"""Handlerele de comenzi Telegram și job-ul de verificare periodică.

Botul e public: oricine îl poate folosi, iar fiecare chat are propriile căutări,
izolate de celelalte (toate interogările din DB sunt filtrate după chat_id).
"""

import asyncio
import html
import logging
import time
from collections import defaultdict

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import Forbidden, RetryAfter, TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes

from config import settings
from database import Database, Search
from scraper import (
    SUPPORTED_SITES, Listing, ScrapeError, build_search_url, is_supported_url, is_url,
    matches_keywords, scrape,
)

log = logging.getLogger(__name__)

HELP_TEXT = (
    "<b>Comenzi disponibile</b>\n"
    "/add &lt;termen&gt; — caută direct termenul\n"
    "    ex: <code>/add iphone 13</code>\n"
    "/add &lt;url&gt; [cuvinte cheie] — monitorizează o pagină de căutare sau categorie, "
    "opțional doar anunțurile care conțin cuvintele în titlu\n"
    "    ex: <code>/add https://www.publi24.ro/anunturi/electronice/telefoane-mobile/ iphone 13</code>\n"
    "/list — căutările tale active\n"
    "/remove &lt;id&gt; — șterge o căutare\n"
    "/check — verifică acum, fără să aștepți intervalul\n"
    "/help — acest mesaj\n\n"
    f"Site-uri suportate: {', '.join(SUPPORTED_SITES)}"
)


def _db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["db"]


def format_listing(listing: Listing, search: Search) -> str:
    lines = [f"🆕 <b>{html.escape(listing.title)}</b>"]
    if listing.price:
        lines.append(f"💰 {html.escape(listing.price)}")
    if listing.location:
        lines.append(f"📍 {html.escape(listing.location)}")
    lines.append(f'🔗 <a href="{html.escape(listing.url)}">Vezi anunțul</a>')
    lines.append(f"<i>#{search.id} · {html.escape(search.label)}</i>")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Logica de verificare
# --------------------------------------------------------------------------- #

class ChatGone(Exception):
    """Utilizatorul a blocat botul sau chat-ul nu mai există."""


async def deliver(app: Application, search: Search, page: list[Listing]) -> int:
    """Trimite anunțurile noi de pe pagină care se potrivesc căutării.
    Returnează câte s-au trimis. Ridică ChatGone dacă chat-ul nu mai e accesibil."""
    db: Database = app.bot_data["db"]
    listings = [l for l in page if matches_keywords(l.title, search.keywords)]
    if not search.seeded:
        # prima citire reușită (ex. /add a fost blocat): marcăm tot, fără alerte
        db.mark_seen(search.chat_id, [l.id for l in listings])
        db.mark_seeded(search.id)
        search.seeded = True
        return 0
    sent = 0
    for listing in listings:
        if db.is_seen(search.chat_id, listing.id):
            continue
        try:
            await app.bot.send_message(
                search.chat_id, format_listing(listing, search), parse_mode=ParseMode.HTML
            )
        except RetryAfter as exc:
            log.warning("Rate limit Telegram, aștept %ss", exc.retry_after)
            await asyncio.sleep(float(exc.retry_after))
            break  # restul anunțurilor rămân nevăzute -> se trimit la următoarea verificare
        except Forbidden as exc:
            raise ChatGone from exc
        except TelegramError as exc:
            log.error("Nu am putut trimite %s: %s", listing.url, exc)
            continue  # nu marcăm ca văzut -> reîncercăm data viitoare
        db.mark_seen(search.chat_id, [listing.id])
        sent += 1
        await asyncio.sleep(1)  # evităm rate-limit-ul Telegram
    return sent


async def run_checks(app: Application, searches: list[Search]) -> int:
    """Verifică o listă de căutări. Fiecare URL e descărcat o singură dată, chiar dacă
    mai mulți utilizatori urmăresc aceeași pagină."""
    db: Database = app.bot_data["db"]
    by_url: dict[str, list[Search]] = defaultdict(list)
    for s in searches:
        by_url[s.url].append(s)

    total, gone = 0, set()
    for url, group in by_url.items():
        try:
            page = await asyncio.to_thread(scrape, url)  # requests e blocant
        except ScrapeError as exc:
            log.warning("%s: %s", url, exc)
            continue
        for search in group:
            if search.chat_id in gone:
                continue
            try:
                total += await deliver(app, search, page)
            except ChatGone:
                gone.add(search.chat_id)

    for chat_id in gone:
        n = db.remove_chat(chat_id)
        log.info("Chat-ul %s a blocat botul: am șters %d căutări.", chat_id, n)
    return total


async def check_all_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    searches = _db(context).list_searches()
    total = await run_checks(context.application, searches)
    log.info("Verificare terminată: %d căutări, %d anunțuri noi.", len(searches), total)


# --------------------------------------------------------------------------- #
# Comenzi
# --------------------------------------------------------------------------- #

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html("👋 Salut! Monitorizez anunțuri pentru tine.\n\n" + HELP_TEXT)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html(HELP_TEXT, disable_web_page_preview=True)


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if not args:
        await update.message.reply_html(HELP_TEXT, disable_web_page_preview=True)
        return

    chat_id = update.effective_chat.id
    db = _db(context)
    if db.count_searches(chat_id) >= settings.max_searches_per_chat:
        await update.message.reply_text(
            f"Ai atins limita de {settings.max_searches_per_chat} căutări. "
            "Șterge una cu /remove înainte să adaugi alta."
        )
        return

    if is_url(args[0]):
        url, keywords = args[0], " ".join(args[1:]).strip()
        # doar site-urile cu parser: altfel oricine ar putea face botul să acceseze
        # orice adresă (inclusiv din rețeaua ta locală)
        if not is_supported_url(url):
            await update.message.reply_text(
                f"Site nesuportat. Pot monitoriza doar: {', '.join(SUPPORTED_SITES)}."
            )
            return
        page = url.split("//", 1)[-1].removeprefix("www.").rstrip("/")[:60]
        label = f"{keywords} @ {page}" if keywords else page
    else:
        # termenul e folosit și ca filtru pe titlu: rezultatele căutării includ
        # anunțuri promovate fără legătură cu termenul
        keywords = label = " ".join(args)[:100]
        url = build_search_url(label)

    search = db.add_search(chat_id, url, label, keywords)
    if search is None:
        await update.message.reply_text("Această căutare există deja. Vezi /list.")
        return

    # Marcăm anunțurile existente ca văzute, ca să primești doar ce apare de acum.
    msg = await update.message.reply_text("⏳ Adaug căutarea și citesc anunțurile existente...")
    try:
        all_listings = await asyncio.to_thread(scrape, url)
        error = None
    except ScrapeError as exc:
        all_listings, error = [], str(exc)
    listings = [l for l in all_listings if matches_keywords(l.title, keywords)]
    if not error:
        db.mark_seen(chat_id, [l.id for l in listings])
        db.mark_seeded(search.id)

    text = (
        f"✅ Căutare adăugată <b>#{search.id}</b>: {html.escape(label)}\n"
        f'<a href="{html.escape(url)}">deschide căutarea</a>\n'
    )
    if error:
        text += (
            f"⛔ Nu am putut citi pagina: {html.escape(error)}.\n"
            "Căutarea rămâne salvată; o poți șterge cu /remove."
        )
    elif listings:
        text += f"Am ignorat {len(listings)} anunțuri existente; te anunț doar de cele noi."
    elif all_listings:
        text += (
            f"Pe pagină sunt {len(all_listings)} anunțuri, dar niciunul nu conține acum "
            f"„{html.escape(keywords)}”. Te anunț când apare unul."
        )
    else:
        text += "⚠️ N-am găsit niciun anunț pe pagină. Verifică dacă link-ul e corect."
    await msg.edit_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    searches = _db(context).list_searches(update.effective_chat.id)
    if not searches:
        await update.message.reply_text("Nicio căutare activă. Adaugă una cu /add.")
        return
    lines = [f"<b>Căutările tale</b> ({len(searches)}/{settings.max_searches_per_chat})"]
    for s in searches:
        lines.append(f'<b>#{s.id}</b> · <a href="{html.escape(s.url)}">{html.escape(s.label)}</a>')
    lines.append("\nȘterge una cu <code>/remove &lt;id&gt;</code>")
    await update.message.reply_html("\n".join(lines), disable_web_page_preview=True)


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    arg = (context.args or [""])[0].lstrip("#")
    if not arg.isdigit():
        await update.message.reply_html("Folosire: <code>/remove &lt;id&gt;</code> (ID-ul din /list)")
        return
    # remove_search filtrează după chat_id: nimeni nu poate șterge căutările altcuiva
    if _db(context).remove_search(update.effective_chat.id, int(arg)):
        await update.message.reply_text(f"🗑️ Căutarea #{arg} a fost ștearsă.")
    else:
        await update.message.reply_text(f"Nu ai o căutare #{arg}. Vezi /list.")


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    last_check: dict[int, float] = context.application.bot_data.setdefault("last_check", {})
    wait = settings.check_cooldown - (time.monotonic() - last_check.get(chat_id, -1e9))
    if wait > 0:
        await update.message.reply_text(f"Prea des. Mai încearcă peste {int(wait) + 1}s.")
        return

    searches = _db(context).list_searches(chat_id)
    if not searches:
        await update.message.reply_text("Nicio căutare activă. Adaugă una cu /add.")
        return
    last_check[chat_id] = time.monotonic()
    await update.message.reply_text("🔎 Verific...")
    if await run_checks(context.application, searches) == 0:
        await update.message.reply_text("Niciun anunț nou.")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Eroare neprevăzută", exc_info=context.error)


# --------------------------------------------------------------------------- #
# Construirea aplicației
# --------------------------------------------------------------------------- #

def build_application(db: Database) -> Application:
    app = Application.builder().token(settings.bot_token).build()
    app.bot_data["db"] = db

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_error_handler(on_error)

    app.job_queue.run_repeating(
        check_all_job, interval=settings.check_interval, first=10, name="check_all"
    )
    return app
