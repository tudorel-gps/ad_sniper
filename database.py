"""Stocare SQLite: căutările fiecărui chat și anunțurile deja trimise."""

import sqlite3
from dataclasses import dataclass


@dataclass
class Search:
    id: int
    chat_id: int
    url: str
    label: str
    keywords: str = ""  # gol = toate anunțurile de pe pagină
    seeded: bool = True  # False = anunțurile existente nu au fost încă marcate ca văzute


SEARCHES_SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    INTEGER NOT NULL,
    url        TEXT NOT NULL,
    keywords   TEXT NOT NULL DEFAULT '',
    label      TEXT NOT NULL,
    seeded     INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (chat_id, url, keywords)
)
"""


class Database:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        with self.conn:
            self._migrate()
            self.conn.execute(SEARCHES_SCHEMA)
            # per chat: același anunț nu e trimis de două ori în același chat,
            # chiar dacă apare în mai multe căutări
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_listings (
                    chat_id    INTEGER NOT NULL,
                    listing_id TEXT NOT NULL,
                    seen_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, listing_id)
                )
                """
            )

    def _migrate(self) -> None:
        """Aduce un tabel `searches` mai vechi (fără `keywords`) la schema curentă.
        Tabelul e reconstruit pentru că se schimbă și constrângerea UNIQUE."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(searches)")}
        if not cols or "keywords" in cols:
            return
        # căutările vechi sunt re-inițializate silențios (seeded=0) dacă nu erau marcate
        seeded = "seeded" if "seeded" in cols else "0"
        self.conn.execute("ALTER TABLE searches RENAME TO searches_old")
        self.conn.execute(SEARCHES_SCHEMA)
        self.conn.execute(
            f"INSERT INTO searches (id, chat_id, url, keywords, label, seeded, created_at) "
            f"SELECT id, chat_id, url, '', label, {seeded}, created_at FROM searches_old"
        )
        self.conn.execute("DROP TABLE searches_old")

    # ---- căutări -------------------------------------------------------- #

    def add_search(self, chat_id: int, url: str, label: str, keywords: str = "") -> Search | None:
        """Returnează căutarea nouă sau None dacă există deja în acest chat."""
        try:
            with self.conn:
                cur = self.conn.execute(
                    "INSERT INTO searches (chat_id, url, keywords, label, seeded) "
                    "VALUES (?, ?, ?, ?, 0)",
                    (chat_id, url, keywords, label),
                )
        except sqlite3.IntegrityError:
            return None
        return Search(cur.lastrowid, chat_id, url, label, keywords, seeded=False)

    def mark_seeded(self, search_id: int) -> None:
        with self.conn:
            self.conn.execute("UPDATE searches SET seeded = 1 WHERE id = ?", (search_id,))

    def remove_search(self, chat_id: int, search_id: int) -> bool:
        with self.conn:
            cur = self.conn.execute(
                "DELETE FROM searches WHERE id = ? AND chat_id = ?", (search_id, chat_id)
            )
        return cur.rowcount > 0

    def count_searches(self, chat_id: int) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM searches WHERE chat_id = ?", (chat_id,)
        ).fetchone()[0]

    def remove_chat(self, chat_id: int) -> int:
        """Șterge toate datele unui chat (ex. utilizatorul a blocat botul)."""
        with self.conn:
            n = self.conn.execute("DELETE FROM searches WHERE chat_id = ?", (chat_id,)).rowcount
            self.conn.execute("DELETE FROM seen_listings WHERE chat_id = ?", (chat_id,))
        return n

    def list_searches(self, chat_id: int | None = None) -> list[Search]:
        sql = "SELECT id, chat_id, url, label, keywords, seeded FROM searches"
        if chat_id is None:
            rows = self.conn.execute(sql + " ORDER BY id")
        else:
            rows = self.conn.execute(sql + " WHERE chat_id = ? ORDER BY id", (chat_id,))
        return [Search(**{**dict(r), "seeded": bool(r["seeded"])}) for r in rows]

    # ---- anunțuri văzute ------------------------------------------------ #

    def is_seen(self, chat_id: int, listing_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM seen_listings WHERE chat_id = ? AND listing_id = ?",
            (chat_id, listing_id),
        ).fetchone()
        return row is not None

    def mark_seen(self, chat_id: int, listing_ids: list[str]) -> None:
        with self.conn:
            self.conn.executemany(
                "INSERT OR IGNORE INTO seen_listings (chat_id, listing_id) VALUES (?, ?)",
                [(chat_id, lid) for lid in listing_ids],
            )

    def close(self) -> None:
        self.conn.close()
