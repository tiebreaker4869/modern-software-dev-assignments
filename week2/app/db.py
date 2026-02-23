from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional


BASE_DIR = Path(__file__).resolve().parents[1]
_default_db = str(BASE_DIR / "data" / "app.db")
DB_PATH = os.getenv("DATABASE_URL", _default_db)


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Open a SQLite connection, yield it, then commit and close.

    Rolls back and closes on any exception, ensuring no connection leaks.
    Foreign key enforcement is enabled on every connection.
    """
    if DB_PATH != ":memory:":
        Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS action_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note_id INTEGER,
                text TEXT NOT NULL,
                done INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (note_id) REFERENCES notes(id)
            );
            """
        )


def insert_note(content: str) -> int:
    with get_db() as conn:
        cursor = conn.execute("INSERT INTO notes (content) VALUES (?)", (content,))
        if cursor.lastrowid is None:
            raise RuntimeError("INSERT INTO notes did not return a row ID")
        return int(cursor.lastrowid)


def list_notes() -> list[sqlite3.Row]:
    with get_db() as conn:
        cursor = conn.execute("SELECT id, content, created_at FROM notes ORDER BY id DESC")
        return list(cursor.fetchall())


def get_note(note_id: int) -> Optional[sqlite3.Row]:
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id, content, created_at FROM notes WHERE id = ?",
            (note_id,),
        )
        return cursor.fetchone()


def insert_action_items(items: list[str], note_id: Optional[int] = None) -> list[int]:
    with get_db() as conn:
        ids: list[int] = []
        for item in items:
            cursor = conn.execute(
                "INSERT INTO action_items (note_id, text) VALUES (?, ?)",
                (note_id, item),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("INSERT INTO action_items did not return a row ID")
            ids.append(int(cursor.lastrowid))
        return ids


def get_action_item(action_item_id: int) -> Optional[sqlite3.Row]:
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id, note_id, text, done, created_at FROM action_items WHERE id = ?",
            (action_item_id,),
        )
        return cursor.fetchone()


def list_action_items(note_id: Optional[int] = None) -> list[sqlite3.Row]:
    with get_db() as conn:
        if note_id is None:
            cursor = conn.execute(
                "SELECT id, note_id, text, done, created_at FROM action_items ORDER BY id DESC"
            )
        else:
            cursor = conn.execute(
                "SELECT id, note_id, text, done, created_at FROM action_items"
                " WHERE note_id = ? ORDER BY id DESC",
                (note_id,),
            )
        return list(cursor.fetchall())


def mark_action_item_done(action_item_id: int, done: bool) -> bool:
    """Update the done flag. Returns True if the row existed, False if not found."""
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE action_items SET done = ? WHERE id = ?",
            (1 if done else 0, action_item_id),
        )
        return cursor.rowcount > 0
