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
    """Add demo data without duplicating posts on repeated runs."""
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
        conn.executemany(
            "INSERT OR IGNORE INTO follow(follower_id, followed_id) VALUES (?,?)",
            [
                (users["alice"], users["bob"]),
                (users["alice"], users["dave"]),
                (users["bob"], users["carol"]),
            ],
        )
        post_ids = [r[0] for r in conn.execute("SELECT id FROM post ORDER BY id")]
        if post_ids:
            conn.executemany(
                'INSERT OR IGNORE INTO "like"(user_id,post_id) VALUES (?,?)',
                [
                    (users["bob"], post_ids[0]),
                    (users["carol"], post_ids[0]),
                    (users["dave"], post_ids[-1]),
                ],
            )
    print(f"Seeded starter samples, follows and likes at {database_path()}")


def seed_demo(path: Path, now: datetime | None = None) -> None:
    """Create a separate demo database and refuse to overwrite existing databases."""
    path = path.resolve()
    if path == DB_PATH.resolve() or path.exists():
        raise ValueError("Choose a new demo path; existing databases are never overwritten.")
    path.parent.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now(UTC)
    init_db(path)
    posts = json.loads((ROOT / "data/demo-posts.json").read_text())

    def stamp(hours):
        """Base all demo timestamps on the same time for reproducible tests."""
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
        # User 6 has no follows to demonstrate the cold-start behavior.
        conn.executemany(
            "INSERT INTO follow(follower_id,followed_id,created_at) VALUES (?,?,?)",
            [
                (1, 2, stamp(500)),
                (1, 4, stamp(500)),
                (2, 3, stamp(500)),
                (3, 5, stamp(500)),
                (4, 2, stamp(500)),
            ],
        )
        likes = [
            (2, 7),
            (3, 7),
            (4, 7),
            (5, 7),
            (6, 7),
            (2, 1),
            (3, 1),
            (5, 1),
            (6, 1),
            (2, 11),
            (3, 11),
            (5, 11),
            (6, 11),
            (3, 16),
            (4, 16),
            (5, 16),
            (6, 16),
            (1, 14),
            (1, 19),
            (2, 2),
            (3, 3),
            (4, 6),
            (5, 12),
            (6, 17),
        ]
        conn.executemany(
            'INSERT INTO "like"(user_id,post_id,created_at) VALUES (?,?,?)',
            [(u, p, stamp(0.5)) for u, p in likes],
        )
    print(f"Created {path}: 6 synthetic users, 30 posts, 5 follows, {len(likes)} likes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", type=Path, help="Create a NEW separate demo SQLite database.")
    args = parser.parse_args()
    if args.demo:
        seed_demo(args.demo)
    else:
        seed()
