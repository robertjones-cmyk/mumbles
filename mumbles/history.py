"""A local SQLite log of everything you dictated, so nothing is ever lost."""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional

from . import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  REAL    NOT NULL,
    text        TEXT    NOT NULL,
    raw_text    TEXT    NOT NULL DEFAULT '',
    mode        TEXT    NOT NULL DEFAULT '',
    engine      TEXT    NOT NULL DEFAULT '',
    model       TEXT    NOT NULL DEFAULT '',
    audio_secs  REAL    NOT NULL DEFAULT 0,
    proc_secs   REAL    NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS entries_created_at ON entries (created_at DESC);
"""


@dataclass
class Entry:
    id: int
    created_at: float
    text: str
    raw_text: str = ""
    mode: str = ""
    engine: str = ""
    model: str = ""
    audio_secs: float = 0.0
    proc_secs: float = 0.0

    @property
    def words(self) -> int:
        return len(self.text.split())


class History:
    def __init__(self, path: Optional[Path] = None, limit: int = 1000) -> None:
        self.path = path or paths.history_file()
        self.limit = limit
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def add(self, text: str, raw_text: str = "", mode: str = "", engine: str = "",
            model: str = "", audio_secs: float = 0.0, proc_secs: float = 0.0) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO entries (created_at, text, raw_text, mode, engine, "
                "model, audio_secs, proc_secs) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (time.time(), text, raw_text, mode, engine, model,
                 audio_secs, proc_secs),
            )
            entry_id = int(cursor.lastrowid)
            if self.limit > 0:
                conn.execute(
                    "DELETE FROM entries WHERE id NOT IN "
                    "(SELECT id FROM entries ORDER BY created_at DESC LIMIT ?)",
                    (self.limit,),
                )
        return entry_id

    def recent(self, count: int = 20) -> List[Entry]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM entries ORDER BY created_at DESC LIMIT ?", (count,)
            ).fetchall()
        return [Entry(**dict(row)) for row in rows]

    def search(self, needle: str, count: int = 20) -> List[Entry]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM entries WHERE text LIKE ? "
                "ORDER BY created_at DESC LIMIT ?",
                (f"%{needle}%", count),
            ).fetchall()
        return [Entry(**dict(row)) for row in rows]

    def stats(self) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(audio_secs), 0) AS secs "
                "FROM entries"
            ).fetchone()
            words = sum(len(r["text"].split()) for r in
                        conn.execute("SELECT text FROM entries").fetchall())
        return {"entries": row["n"], "audio_seconds": row["secs"], "words": words}

    def clear(self) -> int:
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            conn.execute("DELETE FROM entries")
        return int(count)
