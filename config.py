"""Configurare centralizată, citită din variabilele de mediu.

Pe server (ex. Render) variabilele vin din dashboard. Local, pot veni dintr-un
fișier .env, care e opțional și NU suprascrie variabilele deja setate în mediu.
"""

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv e util doar local
    pass
else:
    load_dotenv(override=False)


def _str(name: str, default: str = "") -> str:
    # .strip(): spațiile/newline-urile lipite din greșeală în dashboard strică token-ul
    return os.environ.get(name, default).strip()


def _int(name: str, default: int) -> int:
    raw = _str(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"Variabila {name} trebuie să fie un număr întreg, nu {raw!r}") from None


@dataclass(frozen=True)
class Settings:
    bot_token: str = _str("TELEGRAM_BOT_TOKEN")
    # botul e public: limităm resursele pe care le poate consuma un singur chat
    max_searches_per_chat: int = _int("MAX_SEARCHES_PER_CHAT", 10)
    check_cooldown: int = _int("CHECK_COOLDOWN", 60)  # secunde între /check
    search_template: str = _str("SEARCH_TEMPLATE", "https://www.publi24.ro/anunturi/?q={q}")
    check_interval: int = _int("CHECK_INTERVAL", 300)
    db_path: str = _str("DB_PATH", "sniper.db")
    log_level: str = _str("LOG_LEVEL", "INFO").upper()
    # Render (și alte platforme) setează PORT pentru serviciile web; gol = local, fără server
    port: int = _int("PORT", 0)

    # Setări HTTP pentru scraper
    request_timeout: int = 15
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    )

    def validate(self) -> None:
        if not self.bot_token:
            raise SystemExit(
                "Lipsește TELEGRAM_BOT_TOKEN. Setează-l ca variabilă de mediu "
                "(pe Render: Environment) sau, local, în fișierul .env."
            )
        if ":" not in self.bot_token:
            raise SystemExit("TELEGRAM_BOT_TOKEN pare invalid (format așteptat: 123456:ABC...)")
        if "{q}" not in self.search_template and "{query}" not in self.search_template:
            raise SystemExit("SEARCH_TEMPLATE trebuie să conțină {q} sau {query}")


settings = Settings()
