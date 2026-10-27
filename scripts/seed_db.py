"""Seed existing starter samples, or create a separate classroom demo database."""

import argparse
import json
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.db.database import DB_PATH, database_path, get_connection, init_db

ROOT = Path(__file__).resolve().parent.parent
USERS = ["alice", "bob", "carol", "dave", "erin"]
POSTS = [
    ("alice", "hello world, this is my first post"),
    ("alice", "does anyone else think the feed is chronological only? boring"),
    ("bob", "just shipped a cosine similarity search, feels great"),
    ("carol", "spam spam spam buy now click here"),
    ("dave", "benchmarking my ranker against popularity baseline today"),
    ("erin", "red-team week is going to be brutal, good luck everyone"),
]


def seed() -> None:
    """Extend the original seed without duplicating posts on repeat runs."""
    init_db()
    with closing(get_connection()) as conn, conn:
        for username in USERS:
            conn.execute("INSERT OR IGNORE INTO user(username) VALUES (?)", (username,))
        users = dict(conn.execute("SELECT username, id FROM user"))
        for username, content in POSTS:
            if not conn.execute(
                "SELECT 1 FROM post WHERE user_id=? AND content=?", (users[username], content)
            ).fetchone():
                conn.execute(
                    "INSERT INTO post(user_id, content) VALUES (?, ?)", (users[username], content)
                )
    print(f"Seeded starter samples at {database_path()}")


def seed_demo(path: Path, now: datetime | None = None) -> None:
    """Refuse overwrite; the caller chooses a new, explicitly separate database."""
    path = path.resolve()
    if path == DB_PATH.resolve() or path.exists():
        raise ValueError("Choose a new demo path; existing databases are never overwritten.")
    path.parent.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now(UTC)
    init_db(path)
    posts = json.loads((ROOT / "data/demo-posts.json").read_text())

    def stamp(hours):
        return (now - timedelta(hours=hours)).isoformat()

    with closing(get_connection(path)) as conn, conn:
        conn.executemany(
            "INSERT INTO user(id,username,created_at) VALUES (?,?,?)",
            [
                (i, name, stamp(720))
                for i, name in enumerate(["elena", "mara", "andrei", "ioana", "radu", "teo"], 1)
            ],
        )
        conn.executemany(
            "INSERT INTO post(id,user_id,content,created_at) VALUES (?,?,?,?)",
            [
                (i, author, text, stamp((i * 7) % 100 + 1))
                for i, (author, text) in enumerate(posts, 1)
            ],
        )
    print(f"Created {path}: 6 synthetic users and 30 posts.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", type=Path, help="Create a NEW separate demo SQLite database.")
    args = parser.parse_args()
    if args.demo:
        seed_demo(args.demo)
    else:
        seed()
