"""SQLite reads stay outside search policies."""

from contextlib import closing
from pathlib import Path

from app.db.database import get_connection
from app.domain.models import Post


class SQLitePostRepository:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path

    def all_posts(self) -> list[Post]:
        with closing(get_connection(self.path)) as conn:
            rows = conn.execute(
                "SELECT id, user_id, content, created_at FROM post ORDER BY id"
            ).fetchall()
        return [Post(**dict(row)) for row in rows]
