"""SQLite reads stay outside search and feed policies."""

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.db.database import get_connection
from app.domain.models import Post
from app.learned import HistoricalLike, LearnedSnapshot
from app.ranking import utc


@dataclass
class FeedSnapshot:
    posts: list[Post]
    followed_authors: set[int]
    like_counts: dict[int, int]


class SQLitePostRepository:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path

    def all_posts(self) -> list[Post]:
        with closing(get_connection(self.path)) as conn:
            rows = conn.execute(
                "SELECT id, user_id, content, created_at FROM post ORDER BY id"
            ).fetchall()
        return [Post(**dict(row)) for row in rows]

    def learned_snapshot(self, user_id: int, now: datetime) -> LearnedSnapshot | None:
        """Read a consistent catalogue and history, strictly before now."""
        now = utc(now)
        with closing(get_connection(self.path)) as conn:
            conn.execute("BEGIN")
            if conn.execute("SELECT id FROM user WHERE id = ?", (user_id,)).fetchone() is None:
                return None
            rows = conn.execute(
                "SELECT id, user_id, content, created_at FROM post ORDER BY id"
            ).fetchall()
            posts = [Post(**dict(row)) for row in rows]
            # Compare datetimes in Python to preserve microseconds and timezone offsets.
            posts = [post for post in posts if utc(post.created_at) < now]
            visible_ids = {post.id for post in posts}
            categories = {}
            for row in conn.execute("SELECT post_id, category FROM post_category"):
                if row["post_id"] in visible_ids:
                    categories.setdefault(row["post_id"], set()).add(row["category"])
            likes = []
            for row in conn.execute('SELECT user_id, post_id, created_at FROM "like"'):
                created_at = utc(datetime.fromisoformat(row["created_at"]))
                if row["post_id"] in visible_ids and created_at < now:
                    likes.append(HistoricalLike(row["user_id"], row["post_id"], created_at))
        return LearnedSnapshot(posts, categories, likes)

    def feed_snapshot(self, user_id: int, now: datetime) -> FeedSnapshot | None:
        """Read feed data up to now; None means the user does not exist."""
        cutoff = now.isoformat()
        with closing(get_connection(self.path)) as conn:
            # All reads see the same database snapshot.
            conn.execute("BEGIN")
            if conn.execute("SELECT id FROM user WHERE id = ?", (user_id,)).fetchone() is None:
                return None
            # Include unfollowed authors; exclude own, already-liked, and future posts.
            rows = conn.execute(
                """
                SELECT p.id, p.user_id, p.content, p.created_at FROM post p
                WHERE p.user_id != ? AND julianday(p.created_at) <= julianday(?)
                AND NOT EXISTS (SELECT 1 FROM "like" l WHERE l.user_id = ?
                    AND l.post_id = p.id AND julianday(l.created_at) <= julianday(?))
                ORDER BY p.id
            """,
                (user_id, cutoff, user_id, cutoff),
            ).fetchall()
            followed = conn.execute(
                """SELECT followed_id FROM follow
                WHERE follower_id = ? AND julianday(created_at) <= julianday(?)""",
                (user_id, cutoff),
            ).fetchall()
            # Count only likes known at now to avoid using future data.
            counts = conn.execute(
                """SELECT post_id, count(*) AS n FROM "like"
                WHERE julianday(created_at) <= julianday(?) GROUP BY post_id""",
                (cutoff,),
            ).fetchall()
        return FeedSnapshot(
            [Post(**dict(r)) for r in rows], {r[0] for r in followed}, {r[0]: r[1] for r in counts}
        )
