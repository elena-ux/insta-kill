"""Compare the imported feed with notebook inference; never train or export a model."""

import argparse
import ast
import hashlib
import json
import os
from collections import defaultdict, deque, namedtuple
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from time import perf_counter

import numpy as np
from fastapi.testclient import TestClient

from app.db.database import get_connection
from app.db.repository import SQLitePostRepository
from app.infrastructure.like_model import MODEL_PATH, load_model
from app.learned import build_features, predict
from app.main import create_app
from scripts.seed_db import read_csv, timestamp


def notebook_reference(notebook: Path, source: Path, model: dict):
    """Load only LiveSignals, sigmoid and predict, not notebook execution cells."""
    movies = {int(row["movieId"]): row for row in read_csv(source, "movies.csv")}
    events = [
        (int(r["userId"]), int(r["movieId"]), int(r["timestamp"]), float(r["rating"]))
        for r in read_csv(source, "ratings.csv")
    ]
    first_seen = {}
    for _, movie, time, _ in events:
        first_seen[movie] = min(time, first_seen.get(movie, time))
    movie_ids = sorted(first_seen, key=lambda movie: (first_seen[movie], movie))
    row_of = {movie: row for row, movie in enumerate(movie_ids)}
    genres_by_movie = {
        movie: {g for g in movies[movie]["genres"].split("|") if g != "(no genres listed)"}
        for movie in movie_ids
    }
    genres = sorted(set().union(*genres_by_movie.values()))
    matrix = np.array([[g in genres_by_movie[m] for g in genres] for m in movie_ids], dtype=float)
    Catalogue = namedtuple("Catalogue", "titles first_seen genres n_genres")
    catalogue = Catalogue(
        [movies[m]["title"] for m in movie_ids],
        np.array([first_seen[m] for m in movie_ids]),
        matrix,
        np.maximum(matrix.sum(axis=1), 1),
    )
    Like = namedtuple("Like", "user_id row ts")
    likes = sorted(
        [Like(u, row_of[m], t) for u, m, t, rating in events if rating >= 4],
        key=lambda like: (like.ts, like.user_id, like.row),
    )
    namespace = {
        "np": np,
        "defaultdict": defaultdict,
        "deque": deque,
        "GENRES": genres,
        "DAY": 86400,
        "HALF_LIFE_DAYS": float(model["half_life_days"]),
        "POPULARITY_DAYS": float(model["popularity_days"]),
        "ACTIVITY_CAP": float(model["activity_cap"]),
        "AGE_CAP_DAYS": float(model["age_cap_days"]),
    }
    wanted = {"LiveSignals", "sigmoid", "predict"}
    for cell in json.loads(notebook.read_text())["cells"]:
        if cell["cell_type"] != "code":
            continue
        try:
            tree = ast.parse("".join(cell["source"]))
        except SyntaxError:  # Colab install/upload commands are not Python modules.
            continue
        for node in tree.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in wanted:
                # Execute these definitions from the trusted course notebook only.
                definition = compile(
                    ast.Module(body=[node], type_ignores=[]), str(notebook), "exec"
                )
                exec(definition, namespace)  # noqa: S102
    if not wanted.issubset(namespace):
        raise ValueError("Notebook must contain LiveSignals, sigmoid and predict.")
    return namespace, catalogue, likes, movie_ids, events


def verify(source: Path, database: Path, notebook: Path) -> dict:
    protected = [MODEL_PATH, notebook]
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    model = load_model()
    namespace, catalogue, likes, movie_ids, events = notebook_reference(notebook, source, model)
    repository = SQLitePostRepository(database)
    info = repository.dataset_info("movies")
    assert info["source"] == "movielens"
    movie_rows = {movie: row for row, movie in enumerate(movie_ids)}
    with closing(get_connection(database)) as conn:
        actual_posts = [
            tuple(r)
            for r in conn.execute(
                "SELECT * FROM post WHERE id IN (SELECT post_id FROM movielens_post) ORDER BY id"
            )
        ]
        assert actual_posts == sorted(
            (
                movie,
                info["catalogue_user_id"],
                catalogue.titles[row],
                timestamp(int(catalogue.first_seen[row])),
            )
            for row, movie in enumerate(movie_ids)
        )
        expected_likes = {(u, m, timestamp(t)) for u, m, t, rating in events if rating >= 4}
        assert {
            tuple(r)
            for r in conn.execute(
                'SELECT * FROM "like" WHERE post_id IN (SELECT post_id FROM movielens_post)'
            )
        } == expected_likes
        expected_categories = {
            (movie, genre)
            for row, movie in enumerate(movie_ids)
            for column, genre in enumerate(namespace["GENRES"])
            if catalogue.genres[row, column]
        }
        assert {
            tuple(r)
            for r in conn.execute(
                "SELECT * FROM post_category WHERE post_id IN (SELECT post_id FROM movielens_post)"
            )
        } == expected_categories
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            conn.execute(
                "SELECT count(*) FROM follow WHERE follower_id IN (SELECT user_id FROM movielens_user)"
            ).fetchone()[0]
            == 0
        )

    user_counts = defaultdict(int)
    for user, _, _, _ in events:
        user_counts[user] += 0
    for like in likes:
        user_counts[like.user_id] += 1
    cold = min(user_counts, key=user_counts.get)
    active = max(user_counts, key=user_counts.get)
    users = list(dict.fromkeys([1, 2, active, cold]))
    end = int(datetime.fromisoformat(info["reference_time"]).timestamp())
    times = [int(np.quantile([like.ts for like in likes], q)) for q in (0.70, 0.85)] + [end]
    comparisons, expected_feeds = [], {}
    for time in times:
        state = namespace["LiveSignals"](catalogue, max(user_counts) + 1)
        for like in likes:
            if like.ts < time:
                state.add_like(like)
        state.advance(time)
        for user in users:
            now = datetime.fromtimestamp(time, UTC)
            snapshot = repository.learned_snapshot(user, now, "movies")
            posts, features = build_features(snapshot, user, now, model)
            rows = np.array([movie_rows[post.id] for post in posts], dtype=int)
            expected_ids = {
                movie_ids[row]
                for row in range(len(movie_ids))
                if catalogue.first_seen[row] < time and row not in state.liked[user]
            }
            assert {post.id for post in posts} == expected_ids
            reference = state.features(user, rows, time)
            np.testing.assert_allclose(features, reference, rtol=0, atol=1e-12)
            scores = predict(model, features)
            expected_scores = namespace["predict"](model, reference)
            np.testing.assert_allclose(scores, expected_scores, rtol=0, atol=1e-12)
            comparisons.append(
                {
                    "user_id": user,
                    "at": timestamp(time),
                    "candidates": len(posts),
                    "max_signal_error": float(np.max(np.abs(features - reference))),
                    "max_prediction_error": float(np.max(np.abs(scores - expected_scores))),
                }
            )
            if time == end:
                expected_feeds[user] = sorted(
                    zip([p.id for p in posts], expected_scores),
                    key=lambda pair: (-pair[1], pair[0]),
                )

    previous = os.environ.get("INSTAKILL_DB_PATH")
    os.environ["INSTAKILL_DB_PATH"] = str(database.resolve())
    measurements, examples = [], []
    try:
        with TestClient(create_app()) as client:
            for user in users:
                url = f"/feed?user_id={user}&strategy=learned&limit=20&collection=movies"
                response = client.get(url)  # One warm-up, then five full requests.
                assert response.status_code == 200
                body = response.json()
                expected = expected_feeds[user][:20]
                assert [p["post_id"] for p in body["posts"]] == [p[0] for p in expected]
                np.testing.assert_allclose(
                    [p["score"] for p in body["posts"]],
                    [p[1] for p in expected],
                    rtol=0,
                    atol=1e-12,
                )
                runs = []
                for _ in range(5):
                    started = perf_counter()
                    repeat = client.get(url)
                    runs.append((perf_counter() - started) * 1000)
                    assert repeat.status_code == 200 and repeat.json() == body
                for strategy in ("for_you", "chronological"):
                    assert (
                        client.get(
                            f"/feed?user_id={user}&strategy={strategy}&collection=movies"
                        ).status_code
                        == 200
                    )
                measurements.append({"user_id": user, "runs_ms": runs, "median_ms": median(runs)})
                examples.append({**body, "posts": body["posts"][:5]})
    finally:
        if previous is None:
            os.environ.pop("INSTAKILL_DB_PATH", None)
        else:
            os.environ["INSTAKILL_DB_PATH"] = previous
    assert before == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    return {
        "dataset": info,
        "mapping": "movieId -> post.id; title -> content; genres -> categories; rating >= 4 -> like",
        "source_mapping_passed": True,
        "model_sha256": before[str(MODEL_PATH)],
        "notebook_and_model_unchanged": True,
        "notebook_comparisons": comparisons,
        "cold_start_user": cold,
        "most_active_user": active,
        "request_timing": "FastAPI TestClient, database reads through JSON response; no network; "
        "one warm-up and five measured runs per user",
        "requests": measurements,
        "examples": examples,
        "scope": "Inference parity and application integration, not a new held-out quality evaluation.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--notebook", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = verify(args.source, args.database, args.notebook)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Verified {result['dataset']['posts']} films against notebook signals and predictions.")
    for row in result["requests"]:
        print(f"User {row['user_id']}: full feed median {row['median_ms']:.1f} ms")
