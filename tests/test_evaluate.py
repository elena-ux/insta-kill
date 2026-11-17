"""Week 7 checks use only temporary databases, including the end-to-end replay."""

import base64
import csv
import math
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.application.feed import FeedService
from app.db.database import get_connection, init_db
from app.main import create_app
from scripts import evaluate as evaluation

T = datetime(2026, 1, 10, tzinfo=UTC)


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "fixture.db"
    init_db(path)
    before = (T - timedelta(days=2)).isoformat()
    after = (T + timedelta(days=1)).isoformat()
    with closing(get_connection(path)) as conn, conn:
        conn.executemany(
            "INSERT INTO user VALUES(?,?,?)", [(i, f"user_{i}", before) for i in range(1, 7)]
        )
        conn.executemany(
            "INSERT INTO post VALUES(?,6,?,?)", [(i, f"Post {i}", before) for i in range(1, 16)]
        )
        conn.execute("UPDATE post SET user_id=1 WHERE id=10")
        conn.execute("UPDATE post SET created_at=? WHERE id=7", (T.isoformat(),))
        conn.execute("UPDATE post SET created_at=? WHERE id=8", (after,))
        conn.execute(
            "UPDATE post SET created_at=? WHERE id=9",
            ((T - timedelta(microseconds=1)).isoformat(),),
        )
        history = [(1, p, before) for p in (1, 2, 3)]
        history += [(2, p, before) for p in (1, 2, 4)]
        history += [(3, p, before) for p in (1, 2, 3)]  # No later likes: excluded.
        history += [(4, p, before) for p in (1, 2)]  # Not enough history: excluded.
        future = [
            (1, 5, after),
            (1, 6, after),
            (2, 6, after),
            (4, 6, after),
            (1, 7, after),
            (1, 8, after),
            (1, 4, T.isoformat()),
        ]
        conn.executemany('INSERT INTO "like" VALUES(?,?,?)', history + future)
        conn.executemany(
            "INSERT INTO post_category VALUES(?,'Drama')", [(i,) for i in range(1, 16)]
        )
        conn.execute("INSERT INTO follow VALUES(1,2,?)", (before,))
        conn.execute("INSERT INTO follow VALUES(2,3,?)", (T.isoformat(),))
        conn.execute("INSERT INTO follow VALUES(3,2,?)", (after,))
        conn.execute("INSERT INTO user VALUES(7,'future_user',?)", (after,))
        conn.execute("INSERT INTO post VALUES(16,7,'Future author',?)", (after,))
        conn.execute('INSERT INTO "like" VALUES(7,6,?)', (after,))
    return path


@pytest.mark.parametrize(
    "ranking,relevant,expected",
    [
        ([1, 2, 3], set(), 0),
        ([1, 2, 3], {4}, 0),
        ([1, 2, 3, 4], {1, 2, 3}, 1),
        ([1, 2, 3], {3}, 1 / math.log2(4)),
        (list(range(1, 12)), {11}, 0),
        (list(range(1, 11)), set(range(1, 14)), 1),
        ([], {1}, 0),
        ([1, 2, 3], {1, 3}, (1 + 1 / math.log2(4)) / (1 + 1 / math.log2(3))),
    ],
)
def test_ndcg_known_rankings(ranking, relevant, expected):
    assert evaluation.ndcg_at_10(ranking, relevant) == pytest.approx(expected)


def test_snapshot_removes_all_future_information_without_changing_source(database, tmp_path):
    original = database.read_bytes()
    target = tmp_path / "snapshot.db"
    cutoff, likes, posts, counts, _, _ = evaluation.build_snapshot(database, target, T)
    assert cutoff == T and 7 not in posts and 8 not in posts and 9 in posts
    assert counts == {1: 3, 2: 3, 3: 3, 4: 2}
    assert any(like["created_at"] > T for like in likes)  # Answers kept outside the snapshot.
    with closing(get_connection(target)) as conn:
        for table in ("user", "post", "like", "follow"):
            assert all(
                evaluation.parse_time(r[0]) < T
                for r in conn.execute(f'SELECT created_at FROM "{table}"')
            )
        assert conn.execute("SELECT follower_id,followed_id FROM follow").fetchall()[0][:] == (1, 2)
        assert conn.execute("SELECT count(*) FROM follow").fetchone()[0] == 1
        assert (
            conn.execute("SELECT * FROM post_category WHERE post_id IN (7,8,16)").fetchall() == []
        )
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert database.read_bytes() == original


def test_time_offsets_and_strict_cutoff(database, tmp_path):
    with closing(get_connection(database)) as conn, conn:
        conn.execute("UPDATE follow SET created_at='2026-01-10T02:00:00+02:00' WHERE follower_id=1")
        conn.execute("UPDATE post SET created_at='2026-01-09T19:00:00-05:00' WHERE id=7")
    target = tmp_path / "snapshot.db"
    evaluation.build_snapshot(database, target, T)
    with closing(get_connection(target)) as conn:
        assert conn.execute("SELECT count(*) FROM follow").fetchone()[0] == 0
        assert conn.execute("SELECT id FROM post WHERE id=7").fetchone() is None


def test_default_cutoff_is_80th_percentile(database, tmp_path):
    cutoff, likes, *_ = evaluation.build_snapshot(database, tmp_path / "snapshot.db")
    expected = np.quantile([like["created_at"].timestamp() for like in likes], 0.8)
    assert cutoff.timestamp() == pytest.approx(expected)


def test_replay_calls_the_same_service_as_feed(database, tmp_path, monkeypatch):
    calls = []
    original = FeedService.build

    def counted(self, user_id, now, strategy="for_you", limit=20, collection=None):
        response = original(self, user_id, now, strategy, limit, collection)
        calls.append((self.repository.path, user_id, now, strategy, limit, response))
        return response

    monkeypatch.setattr(FeedService, "build", counted)
    target = tmp_path / "snapshot.db"
    cutoff, likes, posts, counts, *_ = evaluation.build_snapshot(database, target, T)
    results, fresh_users, relevant = evaluation.replay(target, cutoff, likes, posts, counts)
    assert len(calls) == 8
    assert set(results.user_id) == {1, 2}
    assert relevant[1] == {5, 6} and relevant[2] == {6}
    assert results.n_relevant.tolist() == [2] * 4 + [1] * 4
    assert fresh_users == {1, 2}
    assert [(c[1], c[3]) for c in calls] == [
        (user, strategy) for user in (1, 2) for strategy in evaluation.STRATEGIES
    ]
    assert all(path == target and now == T and limit == 10 for path, _, now, _, limit, _ in calls)
    for _, user, _, _, _, response in calls:
        ids = {p.post_id for p in response.posts}
        assert not ids & ({1, 2, 3, 7, 8, 10} if user == 1 else {1, 2, 4, 7, 8})
    monkeypatch.setenv("INSTAKILL_DB_PATH", str(database))
    with TestClient(create_app()) as client:
        assert client.get("/feed?user_id=1&strategy=learned&limit=10").status_code == 200
    assert len(calls) == 9 and calls[-1][3] == "learned"


def test_reports_are_deterministic_and_dashboard_is_self_contained(database, tmp_path):
    original = database.read_bytes()
    for folder in ("first", "second"):
        evaluation.evaluate(database, tmp_path / folder, T, seed=42)
    for name in ("eval_results.csv", "baseline_table.md"):
        assert (tmp_path / "first" / name).read_bytes() == (tmp_path / "second" / name).read_bytes()
    with (tmp_path / "first/eval_results.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 8
    assert list(rows[0]) == ["user_id", "strategy", "ndcg_at_10", "n_relevant", "user_group"]
    dashboard = (tmp_path / "first/dashboard.html").read_text()
    images = re.findall(r"src='data:image/png;base64,([^']+)'", dashboard)
    assert len(images) == 3
    assert all(base64.b64decode(image).startswith(b"\x89PNG") for image in images)
    assert "<script" not in dashboard and "https://" not in dashboard
    assert "No eligible users means no estimate" in dashboard
    assert database.read_bytes() == original


def test_bootstrap_keeps_users_paired_and_handles_empty_groups():
    rows = []
    for user, score in enumerate((0.1, 0.3, 0.5), 1):
        for strategy in evaluation.STRATEGIES:
            value = score + (0.2 if strategy == "learned" else 0)
            rows.append(
                {
                    "user_id": user,
                    "strategy": strategy,
                    "ndcg_at_10": value,
                    "n_relevant": 1,
                    "user_group": evaluation.GROUPS[0],
                }
            )
    results = pd.DataFrame(rows)
    means, differences = evaluation.summarize(results, 42)
    overall = differences.iloc[0]
    assert overall["mean"] == pytest.approx(0.2)
    assert overall.low == pytest.approx(0.2) and overall.high == pytest.approx(0.2)
    assert overall.verdict == "wins"
    assert means.iloc[0].low < means.iloc[0].high
    absent = differences[differences["slice"] == evaluation.GROUPS[3]].iloc[0]
    assert absent.users == 0 and np.isnan(absent["mean"]) and absent.verdict == "unclear"
    results.loc[results.strategy == "learned", "ndcg_at_10"] -= 0.4
    assert evaluation.summarize(results, 42)[1].iloc[0].verdict == "loses"
    results.loc[results.strategy == "learned", "ndcg_at_10"] = [0.1, 0.3, 0.5]
    assert evaluation.summarize(results, 42)[1].iloc[0].verdict == "unclear"


@pytest.mark.parametrize(
    "likes,group", [(3, 0), (9, 0), (10, 1), (49, 1), (50, 2), (199, 2), (200, 3)]
)
def test_activity_boundaries(likes, group):
    assert evaluation.user_group(likes) == evaluation.GROUPS[group]


def test_missing_database_does_not_create_a_file(tmp_path):
    missing = tmp_path / "missing.db"
    with pytest.raises(sqlite3.OperationalError, match="unable to open database"):
        evaluation.build_snapshot(missing, tmp_path / "snapshot.db", T)
    assert not missing.exists()


def test_empty_population_has_a_clear_error(database, tmp_path):
    with pytest.raises(ValueError, match="No users"):
        evaluation.evaluate(database, tmp_path / "report", T - timedelta(days=20))


def test_model_period_overlap_uses_evaluated_movielens_likes():
    likes = [
        {"user_id": 1, "post_id": i, "created_at": evaluation.parse_time(time)}
        for i, time in [(1, "2012-01-01"), (2, "2015-01-01"), (3, "2017-01-01")]
    ]
    results = pd.DataFrame({"user_id": [1]})
    message = evaluation.model_overlap(
        likes, results, {1: {}, 2: {}, 3: {}}, {1, 2, 3}, evaluation.parse_time("2011-01-01")
    )
    assert "1 fall in the training period" in message
    assert "1 fall in the validation period" in message
    assert "Of 3 evaluated later likes, 3 are MovieLens" in message
