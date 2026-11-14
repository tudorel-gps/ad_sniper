"""Preluare și parsare anunțuri de pe site-uri de anunțuri.

Pentru a adăuga un site nou: scrie o funcție `parse_<site>(html, base_url)`
care returnează o listă de `Listing` și înregistreaz-o în `PARSERS`.
"""

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import quote, quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from config import settings

log = logging.getLogger(__name__)


@dataclass
class Listing:
    id: str
    title: str
    url: str
    price: str = ""
    location: str = ""


class ScrapeError(Exception):
    """Pagina nu a putut fi descărcată (blocare, timeout, eroare HTTP)."""


def _stable_id(url: str) -> str:
    """ID derivat din URL (fără query string), folosit când site-ul nu expune unul."""
    clean = url.split("?")[0].split("#")[0]
    return hashlib.sha1(clean.encode()).hexdigest()[:16]


def _text(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def _headers() -> dict:
    return {"User-Agent": settings.user_agent, "Accept-Language": "ro-RO,ro;q=0.9"}


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=_headers(), timeout=settings.request_timeout)
    resp.raise_for_status()
    return resp.text


# --------------------------------------------------------------------------- #
# Filtrare după cuvinte cheie
# --------------------------------------------------------------------------- #

def normalize(text: str) -> str:
    """Litere mici, fără diacritice: „Vând” -> „vand”."""
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def matches_keywords(title: str, keywords: str) -> bool:
    """Toate cuvintele cheie trebuie să apară în titlu, la început de cuvânt.
    ex. „iphone 13” prinde „iPhone 13 Pro” și „IPHONE 13PRO”, dar nu „iPhone 113”."""
    if not keywords.strip():
        return True
    title = normalize(title)
    return all(re.search(r"\b" + re.escape(kw), title) for kw in normalize(keywords).split())


# --------------------------------------------------------------------------- #
# Parsere specifice site-urilor
# --------------------------------------------------------------------------- #

def parse_publi24(html: str, base_url: str) -> list[Listing]:
    """publi24.ro — pagini de căutare (/anunturi/?q=...) și de categorie
    (ex. /anunturi/electronice/telefoane-mobile/)."""
    soup = BeautifulSoup(html, "html.parser")
    listings = []
    for card in soup.select("div.article-item"):
        link = card.select_one(".article-title a[href]")
        if not link:
            continue
        url = urljoin(base_url, link["href"])

        # la anunțurile cu preț redus: <span class="new-price"> + <span class="old-price">
        new, old = card.select_one(".new-price"), card.select_one(".old-price")
        if new:
            price = _text(new) + (f" (era {_text(old)})" if old else "")
        else:
            price = _text(card.select_one(".article-price"))

        listings.append(
            Listing(
                id=card.get("data-articleid") or _stable_id(url),
                title=_text(link),
                url=url,
                price=price,
                location=_text(card.select_one(".article-location")),
            )
        )
    return listings


def parse_olx(html: str, base_url: str) -> list[Listing]:
    """OLX.ro. Atenție: OLX blochează în prezent cererile automate (HTTP 403)."""
    soup = BeautifulSoup(html, "html.parser")
    listings = []
    for card in soup.select('div[data-cy="l-card"]'):
        link = card.select_one("a[href]")
        if not link:
            continue
        url = urljoin(base_url, link["href"])
        listings.append(
            Listing(
                id=card.get("id") or _stable_id(url),
                title=_text(card.select_one("h4, h6")) or _text(link),
                url=url,
                price=_text(card.select_one('[data-testid="ad-price"]')),
                location=_text(card.select_one('[data-testid="location-date"]')),
            )
        )
    return listings


def parse_generic(html: str, base_url: str) -> list[Listing]:
    """Fallback simplu: orice element <article> care conține un link."""
    soup = BeautifulSoup(html, "html.parser")
    listings = []
    for item in soup.select("article"):
        link = item.select_one("a[href]")
        if not link:
            continue
        url = urljoin(base_url, link["href"])
        listings.append(
            Listing(
                id=_stable_id(url),
                title=_text(item.select_one("h1, h2, h3, h4")) or _text(link),
                url=url,
                price=_text(item.select_one(".price, [class*=price]")),
            )
        )
    return listings


# domeniu -> funcție de parsare
PARSERS = {
    "publi24.ro": parse_publi24,
    "olx.ro": parse_olx,
}


def is_url(text: str) -> bool:
    return urlparse(text).scheme in ("http", "https")


def build_search_url(term: str) -> str:
    """Introduce un termen în SEARCH_TEMPLATE.
    {q}     -> parametru de query:   „iphone 13” -> „iphone+13”   (publi24)
    {query} -> segment de cale:      „iphone 13” -> „iphone-13”   (OLX)"""
    words = term.lower().split()
    return settings.search_template.format(
        q=quote_plus(" ".join(words)), query=quote("-".join(words))
    )


SUPPORTED_SITES = list(PARSERS)


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def is_supported_url(url: str) -> bool:
    """Doar https/http către un site care are parser dedicat."""
    return is_url(url) and _host(url) in PARSERS


def get_parser(url: str):
    return PARSERS.get(_host(url), parse_generic)


def scrape(url: str) -> list[Listing]:
    """Descarcă pagina și returnează anunțurile găsite. Ridică ScrapeError la eșec."""
    try:
        html = fetch_html(url)
    except requests.HTTPError as exc:
        status = exc.response.status_code
        if status in (403, 429):
            raise ScrapeError(
                f"site-ul a blocat cererea (HTTP {status}) — probabil protecție anti-bot"
            ) from exc
        raise ScrapeError(f"eroare HTTP {status}") from exc
    except requests.RequestException as exc:
        raise ScrapeError(f"eroare de conexiune: {exc}") from exc
    listings = get_parser(url)(html, url)
    log.debug("%d anunțuri găsite pe %s", len(listings), url)
    return listings
