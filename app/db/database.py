"""SQLite bootstrap and configurable database location."""

import os
import sqlite3
from contextlib import closing
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "instakill.db"

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
CREATE TABLE IF NOT EXISTS post_category (
    post_id INTEGER NOT NULL REFERENCES post(id) ON DELETE CASCADE,
    category TEXT NOT NULL CHECK (length(trim(category)) > 0),
    PRIMARY KEY (post_id, category)
);
CREATE INDEX IF NOT EXISTS ix_like_post ON "like"(post_id, created_at);
CREATE TABLE IF NOT EXISTS dataset_info (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    source TEXT NOT NULL,
    reference_time TEXT NOT NULL,
    catalogue_user_id INTEGER NOT NULL REFERENCES user(id)
);
CREATE TABLE IF NOT EXISTS movielens_post (
    post_id INTEGER PRIMARY KEY REFERENCES post(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS movielens_user (
    user_id INTEGER PRIMARY KEY REFERENCES user(id) ON DELETE CASCADE
);
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
    target = path if path is not None else database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(get_connection(target)) as conn, conn:
        conn.executescript(SCHEMA)
        # Upgrade the earlier MovieLens-only database without changing its records.
        metadata = conn.execute(
            "SELECT source,catalogue_user_id FROM dataset_info WHERE id=1"
        ).fetchone()
        if metadata and metadata["source"] == "movielens":
            conn.execute(
                "INSERT OR IGNORE INTO movielens_post SELECT id FROM post WHERE user_id=?",
                (metadata["catalogue_user_id"],),
            )
            conn.execute(
                "INSERT OR IGNORE INTO movielens_user SELECT id FROM user WHERE id<?",
                (metadata["catalogue_user_id"],),
            )


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {database_path()}")
