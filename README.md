# Telegram Sniper

Bot Telegram care monitorizează site-uri de anunțuri și trimite doar anunțurile noi.
Căutările se gestionează direct din chat.

## Pornire rapidă

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # Linux/macOS: cp .env.example .env
```

1. Creează un bot cu [@BotFather](https://t.me/BotFather) și pune token-ul în `.env`.
2. `python main.py`, apoi trimite-i botului `/start` și adaugă căutări din chat.

Botul e **public**: oricine îl găsește pe Telegram îl poate folosi. Fiecare chat are
căutările lui, izolate (`/list` și `/remove` văd doar căutările chat-ului curent).
Protecții incluse:
- maxim `MAX_SEARCHES_PER_CHAT` căutări per chat (implicit 10) și `CHECK_COOLDOWN` între `/check`;
- `/add <url>` acceptă doar site-urile cu parser (publi24.ro, olx.ro), ca botul să nu poată
  fi folosit pentru a accesa adrese arbitrare;
- o pagină urmărită de mai mulți utilizatori e descărcată o singură dată per verificare;
- dacă cineva blochează botul, căutările lui sunt șterse automat.

## Comenzi

| Comandă | Ce face |
|---|---|
| `/add <url> iphone 13` | Monitorizează o pagină de categorie, doar anunțurile cu „iphone” și „13” în titlu |
| `/add <url>` | Monitorizează toate anunțurile noi de pe pagină |
| `/add iphone 13` | Caută direct termenul cu `SEARCH_TEMPLATE` (implicit căutarea publi24) și filtrează titlurile după el |
| `/list` | Căutările active, cu ID-urile lor |
| `/remove 3` | Șterge căutarea #3 |
| `/check` | Verifică imediat, fără să aștepte `CHECK_INTERVAL` |
| `/help` | Lista comenzilor |

Cuvintele cheie nu țin cont de majuscule sau diacritice și trebuie să apară toate în titlu.

## Site-uri suportate

- **publi24.ro**: căutare directă (`/add iphone 13`) sau pagini de categorie, ex.
  `/add https://www.publi24.ro/anunturi/electronice/telefoane-mobile/ iphone 13`.
  O pagină are ~24 de anunțuri, deci în categoriile foarte aglomerate păstrează `CHECK_INTERVAL` mic (ex. 300s).
- **olx.ro**: parserul există, dar OLX blochează momentan cererile automate (HTTP 403).

Botul nu verifică `robots.txt`. Unele site-uri (inclusiv publi24, pentru căutare) interzic
acolo accesul automat, deci folosirea poate încălca termenii lor. Botul face o singură cerere
per căutare per interval; nu coborî `CHECK_INTERVAL` mult sub 300s.

La `/add`, anunțurile deja existente sunt marcate ca văzute, deci primești alerte doar pentru cele apărute ulterior.

## Structură

| Fișier        | Rol                                                         |
|---------------|-------------------------------------------------------------|
| `config.py`   | Citește setările din variabilele de mediu (`.env` opțional) |
| `database.py` | SQLite: căutările fiecărui chat + anunțurile deja trimise   |
| `scraper.py`  | Descărcare + parsare (publi24, OLX, fallback generic)       |
| `bot.py`      | Comenzile Telegram și job-ul de verificare periodică        |
| `main.py`     | Punctul de pornire (+ health check pe `$PORT` pe Render)    |
| `render.yaml` | Configurația serviciului pe Render (Blueprint)              |
| `Procfile`    | Comanda de pornire pentru Heroku/Railway                    |

## Adăugarea unui site nou

În `scraper.py`, scrie o funcție `parse_site(html, base_url) -> list[Listing]` și adaug-o în `PARSERS`, cu domeniul drept cheie.

## Deploy pe Render

Botul își ia toată configurația din variabile de mediu; fișierul `.env` e doar pentru rulare locală
și nu trebuie urcat (e în `.gitignore`).

1. Urcă proiectul într-un repo GitHub (fără `.env` și `*.db`).
2. Pe [Render](https://dashboard.render.com): **New → Blueprint** și alege repo-ul. Se folosește `render.yaml`.
   Alternativ, **New → Web Service** manual: Build `pip install -r requirements.txt`, Start `python main.py`.
3. La **Environment**, setează `TELEGRAM_BOT_TOKEN` (restul variabilelor au valori implicite, vezi `.env.example`).
4. Oprește botul local înainte: Telegram permite o singură instanță care face polling per token
   (altfel apare eroarea `Conflict: terminated by other getUpdates request`).

Note:
- Render nu citește `Procfile` (e inclus pentru platforme ca Heroku/Railway); comanda din `render.yaml` e aceeași.
- Serviciile web Render trebuie să asculte pe `$PORT`: `main.py` pornește automat un health check minimal
  când `PORT` e setat. Local nu se deschide niciun port.
- **Planul Free** oprește serviciul după ~15 minute fără trafic HTTP, deci botul nu mai primește comenzi
  și nu mai verifică anunțuri. Soluții: un ping extern (ex. UptimeRobot) pe URL-ul serviciului la fiecare
  5–10 minute, sau un plan plătit (ori un **Background Worker**, care nu are nevoie de port).
- **SQLite pe Render:** fără disk persistent, `sniper.db` (căutările și anunțurile văzute) se pierde la
  fiecare redeploy sau restart. Pe un plan plătit adaugă un disk montat la `/var/data` și setează
  `DB_PATH=/var/data/sniper.db` (vezi comentariile din `render.yaml`).
