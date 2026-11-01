"""SQLite bootstrap and configurable database location."""

import os
import sqlite3
from contextlib import closing
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "instakill.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS post (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES user(id),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS follow (
    follower_id INTEGER NOT NULL REFERENCES user(id),
    followed_id INTEGER NOT NULL REFERENCES user(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (follower_id, followed_id),
    CHECK (follower_id != followed_id)
);
CREATE TABLE IF NOT EXISTS "like" (
    user_id INTEGER NOT NULL REFERENCES user(id),
    post_id INTEGER NOT NULL REFERENCES post(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, post_id)
);
CREATE INDEX IF NOT EXISTS ix_like_post ON "like"(post_id, created_at);
"""


def database_path() -> Path:
    return Path(os.environ.get("INSTAKILL_DB_PATH", str(DB_PATH))).expanduser().resolve()


def get_connection(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path if path is not None else database_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: Path | None = None) -> None:
    """Create missing tables and indexes without deleting existing data."""
    with closing(get_connection(path)) as conn, conn:
        conn.executescript(SCHEMA)


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {database_path()}")
