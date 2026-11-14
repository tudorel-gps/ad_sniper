# Ad Sniper — bot Telegram pentru anunțuri noi

Bot de Telegram care urmărește site-uri de anunțuri (în prezent **publi24.ro**) și îți trimite
pe chat **doar anunțurile nou apărute** pentru căutările tale, cu titlu, preț, locație și link.
Căutările se gestionează direct din Telegram (`/add`, `/list`, `/remove`), fără să umbli la cod.

```
🆕 iPhone 13 128GB Blue | Impecabil
💰 1 150 RON
📍 Botosani, Botosani
🔗 Vezi anunțul
#1 · iphone 13
```

**Pe scurt, cum funcționează:** la fiecare `CHECK_INTERVAL` secunde (implicit 5 minute) botul descarcă
pagina fiecărei căutări, extrage anunțurile și le compară cu cele deja trimise, salvate într-o bază de
date SQLite. Ce e nou îți trimite pe Telegram; ce a mai văzut, ignoră. La `/add`, anunțurile care
există deja pe pagină sunt marcate ca văzute, deci primești alerte doar pentru ce apare **după** ce ai
adăugat căutarea.

---

## Cuprins

1. [Ce îți trebuie](#1-ce-îți-trebuie)
2. [Creează botul în Telegram](#2-creează-botul-în-telegram)
3. [Instalare și rulare locală](#3-instalare-și-rulare-locală)
4. [Variabile de mediu (configurare)](#4-variabile-de-mediu-configurare)
5. [Comenzi în Telegram](#5-comenzi-în-telegram)
6. [Rulare în cloud: Render](#6-rulare-în-cloud-render)
7. [Ținerea botului treaz: UptimeRobot](#7-ținerea-botului-treaz-uptimerobot)
8. [Actualizarea botului](#8-actualizarea-botului)
9. [Limitări importante](#9-limitări-importante)
10. [Probleme frecvente](#10-probleme-frecvente)
11. [Structura proiectului și extindere](#11-structura-proiectului-și-extindere)

---

## 1. Ce îți trebuie

- **Python 3.12+** (testat pe 3.13 și 3.14) — [python.org](https://www.python.org/downloads/).
  La instalarea pe Windows bifează *„Add Python to PATH”*.
- **Git** — [git-scm.com](https://git-scm.com/).
- Un cont **Telegram**.
- Pentru cloud: cont **GitHub**, **Render** și (opțional) **UptimeRobot** — toate au plan gratuit.

## 2. Creează botul în Telegram

1. În Telegram, deschide [@BotFather](https://t.me/BotFather) și trimite `/newbot`.
2. Alege un nume (ex. *Ad Sniper*) și un username care se termină în `bot` (ex. `ad_sniper_tudor_bot`).
3. BotFather îți dă un **token** de forma `123456789:ABCdefGh...`. Acesta e `TELEGRAM_BOT_TOKEN`.

> ⚠️ Token-ul e ca o parolă: cine îl are controlează botul. Nu-l pune în cod, în git sau în
> capturi de ecran. Dacă a scăpat, în BotFather: `/revoke` și generezi altul.

Opțional, ca utilizatorii să vadă comenzile în meniu: BotFather → `/setcommands` → alege botul și trimite:
```
add - adaugă o căutare (termen sau link)
list - căutările tale
remove - șterge o căutare după ID
check - verifică acum
help - ajutor
```

## 3. Instalare și rulare locală

```bash
git clone https://github.com/tudorel-gps/ad_sniper.git
cd ad_sniper

python -m venv .venv
.venv\Scripts\activate            # Windows (PowerShell / CMD)
# source .venv/bin/activate       # Linux / macOS

pip install -r requirements.txt

copy .env.example .env            # Windows
# cp .env.example .env            # Linux / macOS
```

Deschide `.env` și pune token-ul la `TELEGRAM_BOT_TOKEN`. Restul valorilor pot rămâne implicite.

Pornire:
```bash
python main.py
```

În terminal trebuie să apară `Bot pornit. Verificare la fiecare 300s.` Trimite-i botului `/start` în
Telegram, apoi `/add iphone 13`. Oprire: **Ctrl+C**.

> Local, botul rulează doar cât e pornit terminalul/calculatorul. Pentru funcționare non-stop,
> vezi [Render](#6-rulare-în-cloud-render).

## 4. Variabile de mediu (configurare)

Botul citește totul din **variabile de mediu**. Local, ele pot sta în fișierul `.env` (opțional,
nu ajunge în git). Pe server (Render) se setează în dashboard, iar `.env` nu există. Dacă o variabilă
e setată și în mediu și în `.env`, câștigă cea din mediu.

| Variabilă | Implicit | Ce face |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — (**obligatoriu**) | Token-ul de la BotFather |
| `CHECK_INTERVAL` | `300` | Secunde între verificările automate. Nu coborî mult sub 300 (încarci site-ul și riști blocarea). |
| `SEARCH_TEMPLATE` | `https://www.publi24.ro/anunturi/?q={q}` | Pagina folosită de `/add <termen>`. `{q}` → `iphone+13`, `{query}` → `iphone-13` |
| `MAX_SEARCHES_PER_CHAT` | `10` | Câte căutări poate avea un chat |
| `CHECK_COOLDOWN` | `60` | Secunde minime între două `/check` din același chat |
| `DB_PATH` | `sniper.db` | Fișierul SQLite. Pe Render cu disk: `/var/data/sniper.db` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `PORT` | — | Setat automat de Render. Dacă există, botul deschide un health check HTTP pe acest port. Local nu-l seta. |

Valorile greșite opresc botul cu un mesaj clar (ex. *„CHECK_INTERVAL trebuie să fie un număr întreg”*).

## 5. Comenzi în Telegram

| Comandă | Exemplu | Ce face |
|---|---|---|
| `/add <termen>` | `/add iphone 13` | Caută termenul pe publi24 și te anunță de anunțurile noi care au **toate** cuvintele în titlu |
| `/add <link>` | `/add https://www.publi24.ro/anunturi/electronice/telefoane-mobile/` | Urmărește o pagină de căutare sau categorie (cu filtrele tale de pe site: preț, oraș...) |
| `/add <link> <cuvinte>` | `/add https://www.publi24.ro/anunturi/electronice/telefoane-mobile/ iphone 13` | Aceeași pagină, dar doar anunțurile cu cuvintele în titlu |
| `/list` | | Căutările tale, cu ID-uri |
| `/remove <id>` | `/remove 3` | Șterge căutarea #3 |
| `/check` | | Verifică acum, fără să aștepți intervalul |
| `/help`, `/start` | | Ajutor |

**Filtrul de cuvinte:** nu ține cont de majuscule și diacritice (`vand` = `Vând`) și potrivește
începutul cuvintelor: `iphone 13` prinde *„iPhone 13 Pro”* și *„IPHONE 13PRO”*, dar nu *„iPhone 113”*.

**Cine poate folosi botul:** oricine îl găsește pe Telegram. Fiecare chat are căutările lui, izolate:
nimeni nu vede și nu poate șterge căutările altcuiva. Protecții incluse:
- limită de căutări per chat și pauză între `/check`;
- `/add <link>` acceptă doar site-urile suportate (publi24.ro, olx.ro), ca botul să nu poată fi folosit
  pentru a accesa adrese arbitrare;
- o pagină urmărită de mai mulți utilizatori e descărcată o singură dată per verificare;
- dacă cineva blochează botul, căutările lui se șterg automat.

## 6. Rulare în cloud: Render

Render rulează botul non-stop pe un server, din codul de pe GitHub. Proiectul conține deja tot ce
trebuie: `render.yaml` (configurația serviciului), `requirements.txt` (versiuni fixate) și un health
check pe `$PORT` (Render cere ca serviciile *web* să asculte pe un port).

### Primul deploy

1. Codul trebuie să fie pe GitHub (repo-ul `tudorel-gps/ad_sniper`).
2. Intră pe [dashboard.render.com](https://dashboard.render.com) și loghează-te cu GitHub.
3. **New → Blueprint** → alege repo-ul `ad_sniper`.
   Dacă nu apare, apasă *Configure GitHub App* și dă-i acces lui Render la repo.
4. Render citește `render.yaml` și îți cere valoarea pentru **`TELEGRAM_BOT_TOKEN`** → pune token-ul → **Apply**.
5. **Oprește botul local** (Ctrl+C) — Telegram permite un singur bot activ pe token (vezi [Probleme frecvente](#10-probleme-frecvente)).
6. Deschide serviciul → **Logs**. După build trebuie să vezi:
   ```
   Health check pe portul 10000
   Bot pornit. Verificare la fiecare 300s. DB: sniper.db
   ```
7. Trimite `/start` botului în Telegram.

URL-ul serviciului apare sus în pagina lui, de forma `https://telegram-sniper-xxxx.onrender.com`.
Deschis în browser, afișează `ok` — îl vei folosi la UptimeRobot.

<details>
<summary>Alternativă: creare manuală (fără Blueprint)</summary>

**New → Web Service** → alege repo-ul, apoi:
- Runtime: **Python 3**
- Build Command: `pip install -r requirements.txt`
- Start Command: `python main.py`
- Instance Type: **Free**
- Environment: `TELEGRAM_BOT_TOKEN` = token-ul tău, `PYTHON_VERSION` = `3.13.5`
- (Advanced) Health Check Path: `/`
</details>

### Modificarea variabilelor pe Render

Serviciu → **Environment** → editezi / adaugi variabile (vezi [tabelul](#4-variabile-de-mediu-configurare))
→ **Save Changes**. Render repornește botul automat.

> `Procfile` (`web: python main.py`) e inclus pentru platforme ca Heroku/Railway. Render **nu** îl
> citește; folosește `render.yaml` sau comenzile setate în dashboard.

## 7. Ținerea botului treaz: UptimeRobot

Pe planul **Free**, Render **oprește serviciul după ~15 minute fără trafic HTTP**. Mesajele din
Telegram nu contează ca trafic (botul le cere el de la Telegram), deci un bot nefolosit adoarme:
nu mai răspunde la comenzi și nu mai verifică anunțuri. Soluția gratuită: un serviciu extern care
accesează URL-ul botului la fiecare 5 minute.

1. Fă cont pe [uptimerobot.com](https://uptimerobot.com) (planul Free e suficient).
2. **+ New monitor**:
   - Monitor Type: **HTTP(s)**
   - Friendly Name: `ad_sniper`
   - URL: URL-ul serviciului de pe Render, ex. `https://telegram-sniper-xxxx.onrender.com/`
   - Monitoring Interval: **5 minutes**
3. **Create Monitor**. În câteva minute statusul devine **Up** (verde).

Bonus: UptimeRobot îți trimite email dacă botul pică (status **Down**), deci afli imediat.

> Planul Free Render are 750 de ore de rulare pe lună per cont — suficient pentru **un** serviciu
> pornit non-stop (~720 h). Două servicii treze permanent pe același cont nu încap.

## 8. Actualizarea botului

După orice modificare în cod:
```bash
git add -A
git commit -m "ce ai schimbat"
git push
```
Render face **redeploy automat** la fiecare `push` pe `main` (vezi **Events** / **Logs** în dashboard).

> Atenție: pe planul Free, fiecare redeploy **șterge baza de date** (vezi mai jos).

## 9. Limitări importante

- **Baza de date se pierde pe Render Free.** Disk-ul serverului e temporar: la fiecare redeploy sau
  restart, `sniper.db` (căutările tuturor utilizatorilor + anunțurile văzute) e șters și trebuie
  refăcute căutările cu `/add`. Pentru persistență: plan plătit + disk. În `render.yaml`, decomentează
  secțiunea `disk` și variabila `DB_PATH=/var/data/sniper.db`.
- **OLX blochează boții.** Parserul OLX există, dar OLX răspunde cu `HTTP 403` la cererile automate.
  Botul îți spune clar asta la `/add`. Folosește publi24.
- **O pagină are ~24 de anunțuri.** Într-o categorie foarte aglomerată, dacă între două verificări apar
  mai mult de 24 de anunțuri noi, cele care ies de pe prima pagină sunt ratate. Folosește căutări sau
  filtre mai specifice și păstrează `CHECK_INTERVAL` la ~300 s.
- **Termenii site-urilor.** Botul nu verifică `robots.txt`; publi24 interzice acolo accesul automat
  la căutare. Botul face o singură cerere per căutare per interval, dar folosirea poate încălca
  termenii site-ului — e responsabilitatea ta.
- **Structura site-urilor se schimbă.** Dacă `/add` spune *„N-am găsit niciun anunț pe pagină”* pentru
  o pagină care sigur are anunțuri, probabil s-a schimbat HTML-ul site-ului și selectorii din
  `scraper.py` trebuie actualizați.

## 10. Probleme frecvente

| Simptom | Cauză / soluție |
|---|---|
| `Lipsește TELEGRAM_BOT_TOKEN` | Local: lipsește din `.env`. Render: lipsește din **Environment**. |
| `InvalidToken` / `Unauthorized` | Token greșit sau revocat. Copiază-l din nou din BotFather. |
| `Conflict: terminated by other getUpdates request` | Botul rulează în două locuri cu același token (ex. local + Render). Oprește una dintre instanțe. Apare scurt și la un redeploy — e normal. |
| Botul nu răspunde deloc pe Render | Serviciul a adormit (vezi [UptimeRobot](#7-ținerea-botului-treaz-uptimerobot)) sau a picat — vezi **Logs**. |
| Deploy eșuat cu *„No open ports detected”* | Serviciul a fost creat fără `PORT`/health check — asigură-te că rulează `python main.py` din acest repo (versiunea curentă). |
| `⛔ site-ul a blocat cererea (HTTP 403)` | Site-ul blochează boții (ex. OLX). Nu se poate rezolva din bot. |
| `Site nesuportat` la `/add <link>` | Doar publi24.ro și olx.ro sunt acceptate. Vezi [extindere](#11-structura-proiectului-și-extindere). |
| Căutările au dispărut | Redeploy/restart pe Render Free → DB ștearsă (vezi [Limitări](#9-limitări-importante)). |
| Diacritice stricate în terminal (Windows) | Rezolvat automat în `main.py`; dacă persistă, rulează `chcp 65001` înainte. |

## 11. Structura proiectului și extindere

| Fișier | Rol |
|---|---|
| `main.py` | Punctul de pornire: logging, health check pe `$PORT`, pornește botul |
| `bot.py` | Comenzile Telegram și verificarea periodică (JobQueue din python-telegram-bot) |
| `scraper.py` | Descărcarea paginilor, parserele per site, filtrul de cuvinte cheie |
| `database.py` | SQLite: căutările fiecărui chat + anunțurile deja trimise; migrări automate |
| `config.py` | Citește și validează variabilele de mediu |
| `requirements.txt` | Dependențe cu versiuni fixate |
| `render.yaml` | Configurația serviciului pe Render (Blueprint) |
| `Procfile` | Comanda de pornire pentru Heroku/Railway |
| `.env.example` | Model pentru `.env` local |

**Tehnologii:** Python, [python-telegram-bot](https://python-telegram-bot.org/) 22 (async, polling),
requests + BeautifulSoup pentru scraping, SQLite.

### Adăugarea unui site nou

În `scraper.py`:
1. Scrie o funcție `parse_<site>(html, base_url) -> list[Listing]` care extrage din pagină, pentru
   fiecare anunț: un `id` stabil, `title`, `url` și opțional `price`, `location`
   (vezi `parse_publi24` ca model).
2. Adaug-o în dicționarul `PARSERS`, cu domeniul drept cheie: `"exemplu.ro": parse_exemplu`.

Domeniul devine automat acceptat la `/add <link>` și apare în `/help`.
