import random
from contextlib import closing
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.application.feed import FeedService, affinity, freshness, popularity
from app.db.database import get_connection
from app.db.repository import SQLitePostRepository
from app.domain.models import Post
from app.main import create_app
from app.ranking import FeedSignals, FeedWeights, rank_feed
from scripts.seed_db import seed_demo

NOW = datetime(2026, 10, 26, 16, 0, tzinfo=UTC)


def test_signals_on_a_small_example():
    assert freshness(NOW, NOW) == 1.0
    assert freshness(NOW - timedelta(hours=72), NOW) == 0.5
    assert affinity(2, {2, 4}) == 1.0
    assert affinity(3, {2, 4}) == 0.0
    assert popularity(2, 4) == 0.5
    assert popularity(0, 0) == 0.0


def test_heap_ranking_ties_determinism_and_immutability():
    posts = [Post(id=i, user_id=2, content=str(i), created_at=NOW) for i in [12, 7, 21, 3]]
    signals = {p.id: FeedSignals(0.5, 1, 0.5) for p in posts}
    before = deepcopy((posts, signals))
    assert [h.post.id for h in rank_feed(posts, signals, NOW, FeedWeights(), 3)] == [3, 7, 12]
    assert rank_feed(posts, signals, NOW, FeedWeights(), 3) == rank_feed(
        list(reversed(posts)), signals, NOW, FeedWeights(), 3
    )
    assert before == (posts, signals)
    assert rank_feed(posts, signals, NOW, FeedWeights(), 0) == []
    assert len(rank_feed(posts, signals, NOW, FeedWeights(), 50)) == 4
    assert rank_feed([], {}, NOW, FeedWeights(), 5) == []


def test_heap_matches_full_sort_reference_and_excludes_future():
    rng = random.Random(42)
    posts = [
        Post(id=i, user_id=2, content=str(i), created_at=NOW - timedelta(hours=i))
        for i in range(1, 1001)
    ]
    signals = {p.id: FeedSignals(rng.random(), rng.random(), rng.random()) for p in posts}
    expected = sorted(
        posts,
        key=lambda p: (
            -(signals[p.id].freshness + 2 * signals[p.id].affinity + signals[p.id].popularity),
            p.id,
        ),
    )[:10]
    assert [h.post.id for h in rank_feed(posts, signals, NOW, FeedWeights(), 10)] == [
        p.id for p in expected
    ]
    assert (
        rank_feed(
            [Post(id=2000, user_id=2, content="future", created_at=NOW + timedelta(days=1))],
            {},
            NOW,
            FeedWeights(),
            5,
        )
        == []
    )


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / "demo.db"
    seed_demo(path, NOW)
    monkeypatch.setenv("INSTAKILL_DB_PATH", str(path))
    return path


def test_seeded_feed_strategies_exclusions_and_cold_start(database):
    service = FeedService(SQLitePostRepository(database))
    personal = service.build(1, NOW, limit=50)
    latest = service.build(1, NOW, "chronological", 50)
    ids = [p.post_id for p in personal.posts]
    assert 30 not in ids and 14 not in ids and 19 not in ids
    assert ids[0] == 1 and personal.posts[0].score > 0
    assert [p.post_id for p in latest.posts] != ids
    assert all(p.score is None for p in latest.posts)
    assert [p.created_at for p in latest.posts] == sorted(
        [p.created_at for p in latest.posts], reverse=True
    )
    assert service.build(6, NOW).posts  # no follows: global eligible posts, affinity zero


@pytest.mark.parametrize("weights", [FeedWeights(), FeedWeights(10, 20, 0)])
def test_popularity_ranks_only_by_likes_and_breaks_ties_by_id(database, weights):
    service = FeedService(SQLitePostRepository(database), weights=weights)
    posts = service.build(1, NOW, "popularity", 5).posts
    # Post 7 has 5 likes; 1, 11, and 16 have 4; post 2 has 1.
    assert [p.post_id for p in posts] == [7, 1, 11, 16, 2]
    assert [p.score for p in posts] == [1.0, 0.8, 0.8, 0.8, 0.2]
    all_posts = service.build(1, NOW, "popularity", 50).posts
    assert len(all_posts) == 27
    assert not {14, 19, 30} & {p.post_id for p in all_posts}
    assert service.build(6, NOW, "popularity").posts  # No follows needed.


def test_popularity_without_likes_and_without_posts(database):
    service = FeedService(SQLitePostRepository(database))
    with closing(get_connection(database)) as c, c:
        c.execute('DELETE FROM "like"')
    posts = service.build(1, NOW, "popularity", 5).posts
    assert [p.post_id for p in posts] == [1, 2, 3, 4, 5]
    assert all(p.score == 0 for p in posts)
    with closing(get_connection(database)) as c, c:
        c.execute("DELETE FROM post")
    assert service.build(1, NOW, "popularity").posts == []


@pytest.mark.parametrize("strategy", ["for_you", "chronological", "popularity"])
def test_snapshot_hides_future_likes_follows_and_posts(database, strategy):
    repo = SQLitePostRepository(database)
    before = FeedService(repo).build(1, NOW, strategy)
    future = (NOW + timedelta(days=1)).isoformat()
    with closing(get_connection(database)) as c, c:
        c.execute('INSERT INTO "like" VALUES(1,7,?)', (future,))
        c.execute("INSERT INTO follow VALUES(1,5,?)", (future,))
        c.execute(
            "INSERT INTO post(id,user_id,content,created_at) VALUES(31,2,?,?)",
            ("Future post", future),
        )
    assert before == FeedService(repo).build(1, NOW, strategy)


def test_chronological_ties_use_ascending_id(database):
    with closing(get_connection(database)) as c, c:
        c.execute("UPDATE post SET created_at=?", (NOW.isoformat(),))
    ids = [
        p.post_id
        for p in FeedService(SQLitePostRepository(database))
        .build(1, NOW, "chronological", 50)
        .posts
    ]
    assert ids == sorted(ids)


def test_seeded_feed_api(database):
    with TestClient(create_app()) as client:
        result = client.get("/feed", params={"user_id": 1})
        assert result.status_code == 200
        data = result.json()
        assert data["user_id"] == 1 and data["strategy"] == "for_you" and len(data["posts"]) == 20
        assert all(
            {"post_id", "user_id", "content", "created_at", "score"} <= p.keys()
            for p in data["posts"]
        )
        latest = client.get(
            "/feed", params={"user_id": 1, "strategy": "chronological", "limit": 3}
        ).json()
        assert len(latest["posts"]) == 3 and "score" not in latest["posts"][0]
        popular = client.get("/feed?user_id=1&strategy=popularity&limit=5")
        assert popular.status_code == 200
        assert popular.json()["strategy"] == "popularity"
        assert [p["post_id"] for p in popular.json()["posts"]] == [7, 1, 11, 16, 2]
        assert [p["score"] for p in popular.json()["posts"]] == [1.0, 0.8, 0.8, 0.8, 0.2]
        assert client.get("/feed?user_id=999&strategy=popularity").status_code == 404
        assert client.get("/feed?user_id=999").status_code == 404
        for query in [
            "",
            "?user_id=0",
            "?user_id=1&limit=51",
            "?user_id=1&limit=0",
            "?user_id=1&strategy=bad",
            "?user_id=x",
        ]:
            assert client.get("/feed" + query).status_code == 422
