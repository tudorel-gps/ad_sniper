"""Telegram Sniper — monitorizează anunțuri noi și trimite alerte pe Telegram.

Utilizare:
    python main.py

Căutările se gestionează din chat: /add, /list, /remove, /check, /help.
"""

import logging
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bot import build_application
from config import settings
from database import Database

log = logging.getLogger("sniper")


class _HealthHandler(BaseHTTPRequestHandler):
    """Răspunde „ok” la orice GET/HEAD — pentru health check-ul platformei."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"ok")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):  # fără log pentru fiecare ping
        pass


def start_health_server(port: int) -> None:
    """Serviciile „web” de pe Render trebuie să asculte pe $PORT, altfel deploy-ul
    eșuează. Botul folosește polling și nu are nevoie de port, deci deschidem un
    server minimal într-un thread separat."""
    server = ThreadingHTTPServer(("0.0.0.0", port), _HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True, name="health").start()
    log.info("Health check pe portul %s", port)


def main() -> None:
    # consola Windows (cp1252) nu poate afișa diacriticele românești
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)  # altfel loghează fiecare poll

    settings.validate()

    db_dir = os.path.dirname(settings.db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)  # ex. DB_PATH=/var/data/sniper.db pe un disk Render

    if settings.port:
        start_health_server(settings.port)

    db = Database(settings.db_path)
    try:
        app = build_application(db)
        log.info(
            "Bot pornit. Verificare la fiecare %ss. DB: %s", settings.check_interval, settings.db_path
        )
        # drop_pending_updates: la redeploy ignorăm comenzile trimise cât botul era oprit
        app.run_polling(drop_pending_updates=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
