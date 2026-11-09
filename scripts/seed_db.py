"""Create one application database with MovieLens and community collections."""

import argparse
import csv
import io
import json
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

from app.db.database import DB_PATH, get_connection, init_db

FIXTURE = Path(__file__).resolve().parent.parent / "data" / "community.json"


def read_csv(source: Path, name: str) -> list[dict]:
    """Accept either the original ZIP or a directory containing the CSV files."""
    if source.is_dir():
        text = (source / name).read_text(encoding="utf-8-sig")
    else:
        with ZipFile(source) as archive:
            matches = [path for path in archive.namelist() if Path(path).name == name]
            if len(matches) != 1:
                raise ValueError(f"Expected one {name} in the MovieLens archive.")
            text = archive.read(matches[0]).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def timestamp(seconds: int) -> str:
    return datetime.fromtimestamp(seconds, UTC).isoformat()


def import_movielens(source: Path, database: Path) -> dict:
    if database.exists():
        raise ValueError("Choose a new database path; existing databases are never overwritten.")
    movies = {int(row["movieId"]): row for row in read_csv(source, "movies.csv")}
    ratings = read_csv(source, "ratings.csv")
    if not ratings:
        raise ValueError("MovieLens ratings.csv is empty.")

    first_seen, users, likes, pairs = {}, {}, [], set()
    for row in ratings:
        user, movie = int(row["userId"]), int(row["movieId"])
        time, rating = int(row["timestamp"]), float(row["rating"])
        if user <= 0 or movie not in movies or not 0.5 <= rating <= 5:
            raise ValueError("Invalid user, movie or rating in MovieLens data.")
        if (user, movie) in pairs:
            raise ValueError("Duplicate user/movie rating in MovieLens data.")
        pairs.add((user, movie))
        first_seen[movie] = min(time, first_seen.get(movie, time))
        users[user] = min(time, users.get(user, time))
        if rating >= 4:
            likes.append((user, movie, timestamp(time)))

    # MovieLens has no post authors. A catalogue account avoids inventing ownership.
    catalogue_user = max(users) + 1
    reference_time = timestamp(max(int(row["timestamp"]) for row in ratings) + 1)
    posts = [
        (movie, catalogue_user, movies[movie]["title"], timestamp(time))
        for movie, time in sorted(first_seen.items())
    ]
    categories = [
        (movie, genre)
        for movie in sorted(first_seen)
        for genre in movies[movie]["genres"].split("|")
        if genre and genre != "(no genres listed)"
    ]
    database.parent.mkdir(parents=True, exist_ok=True)
    init_db(database)
    with closing(get_connection(database)) as conn, conn:
        conn.executemany(
            "INSERT INTO user(id,username,created_at) VALUES(?,?,?)",
            [(user, f"movielens_{user}", timestamp(time)) for user, time in sorted(users.items())]
            + [(catalogue_user, "movielens_catalogue", timestamp(min(first_seen.values())))],
        )
        conn.executemany("INSERT INTO post VALUES(?,?,?,?)", posts)
        conn.executemany("INSERT INTO post_category VALUES(?,?)", categories)
        conn.executemany('INSERT INTO "like" VALUES(?,?,?)', likes)
        conn.executemany("INSERT INTO movielens_post VALUES(?)", [(p[0],) for p in posts])
        conn.executemany("INSERT INTO movielens_user VALUES(?)", [(u,) for u in users])
        conn.execute(
            "INSERT INTO dataset_info VALUES(1,'movielens',?,?)",
            (reference_time, catalogue_user),
        )
    return {
        "source": "MovieLens latest-small",
        "posts": len(posts),
        "users": len(users),
        "catalogue_user_id": catalogue_user,
        "likes": len(likes),
        "categories": len({genre for _, genre in categories}),
        "reference_time": reference_time,
    }


def add_community(database: Path, now: datetime, include_starter: bool = False) -> None:
    data = json.loads(FIXTURE.read_text())
    with closing(get_connection(database)) as conn, conn:
        user_offset = conn.execute("SELECT coalesce(max(id),0) FROM user").fetchone()[0]
        post_offset = conn.execute("SELECT coalesce(max(id),0) FROM post").fetchone()[0]

        def stamp(hours):
            return (now - timedelta(hours=hours)).isoformat()

        conn.executemany(
            "INSERT INTO user VALUES(?,?,?)",
            [(user_offset + i, name, stamp(720)) for i, name in enumerate(data["users"], 1)],
        )
        conn.executemany(
            "INSERT INTO post VALUES(?,?,?,?)",
            [
                (
                    post_offset + i,
                    user_offset + post["author"],
                    post["content"],
                    stamp((i * 7) % 100 + 1),
                )
                for i, post in enumerate(data["posts"], 1)
            ],
        )
        conn.executemany(
            "INSERT INTO post_category VALUES(?,?)",
            [
                (post_offset + i, category)
                for i, post in enumerate(data["posts"], 1)
                for category in post["categories"]
            ],
        )
        conn.executemany(
            "INSERT INTO follow VALUES(?,?,?)",
            [(user_offset + a, user_offset + b, stamp(500)) for a, b in data["follows"]],
        )
        conn.executemany(
            'INSERT INTO "like" VALUES(?,?,?)',
            [(user_offset + user, post_offset + post, stamp(0.5)) for user, post in data["likes"]],
        )
        if include_starter:
            user_offset += len(data["users"])
            post_offset += len(data["posts"])
            conn.executemany(
                "INSERT INTO user VALUES(?,?,?)",
                [
                    (user_offset + user["id"], user["username"], user["created_at"])
                    for user in data["starter"]["users"]
                ],
            )
            conn.executemany(
                "INSERT INTO post VALUES(?,?,?,?)",
                [
                    (
                        post_offset + post["id"],
                        user_offset + post["user_id"],
                        post["content"],
                        post["created_at"],
                    )
                    for post in data["starter"]["posts"]
                ],
            )


def seed_demo(path: Path, now: datetime | None = None) -> None:
    """Small temporary fixture for unit tests; the application uses the full database."""
    if path.exists():
        raise ValueError("Existing databases are never overwritten.")
    init_db(path)
    add_community(path, now or datetime.now(UTC))


def setup_demo(source: Path, database: Path = DB_PATH) -> None:
    if database.exists():
        with closing(get_connection(database)) as conn:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name='movielens_post'"
            ).fetchone()
            movies = (
                conn.execute("SELECT count(*) FROM movielens_post").fetchone()[0] if exists else 0
            )
            total = conn.execute("SELECT count(*) FROM post").fetchone()[0]
            if 0 < movies < total:
                print(f"Using existing application database: {database}")
                return
        raise ValueError("The destination already exists. Choose a new path; no data was changed.")
    import_movielens(source, database)
    add_community(database, datetime.now(UTC), include_starter=True)
    print(f"Created application database: {database}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", required=True, type=Path, help="MovieLens ZIP or CSV directory."
    )
    parser.add_argument("--database", type=Path, default=DB_PATH)
    args = parser.parse_args()
    setup_demo(args.source, args.database)
