"""Independent notebook examples plus API/database integration for Week 5."""

import json
from contextlib import closing
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.application.feed import FeedService
from app.db.database import get_connection, init_db
from app.db.repository import SQLitePostRepository
from app.domain.models import Post
from app.infrastructure.like_model import MODEL_PATH, LearnedUnavailable, load_model
from app.learned import (
    FEATURES,
    HistoricalLike,
    LearnedSnapshot,
    build_features,
    predict,
    rank_learned,
)
from app.main import create_app
from scripts.seed_db import seed_demo

NOW = datetime(2026, 11, 8, 12, tzinfo=UTC)


@pytest.fixture
def model():
    return load_model()


@pytest.fixture
def small_world():
    posts = [
        Post(id=i, user_id=8, content=f"Post {i}", created_at=NOW - timedelta(days=1095))
        for i in range(1, 9)
    ]
    categories = {
        1: {"Drama"},
        2: {"Drama"},
        3: {"Drama"},
        4: {"Comedy"},
        5: {"Drama"},
        6: {"Drama", "Comedy"},
        7: {"Drama"},
    }
    likes = [HistoricalLike(8, 7, NOW - timedelta(days=400))]
    likes += [HistoricalLike(7, i, NOW - timedelta(days=10)) for i in range(1, 5)]
    likes += [
        HistoricalLike(8, 5, NOW - timedelta(days=10)),
        HistoricalLike(9, 5, NOW - timedelta(days=5)),
    ]
    return LearnedSnapshot(posts, categories, likes)


def test_notebook_example_all_six_signals_and_missing_categories(small_world, model):
    before = deepcopy(small_world)
    posts, features = build_features(small_world, 7, NOW, model)
    assert [p.id for p in posts] == [5, 6, 7, 8]
    np.testing.assert_allclose(
        features[0], [0.5, 0.75, 1, np.log1p(4) / np.log1p(500), 1, 1095 / 9125]
    )
    assert features[1, 1] == 0.5  # Drama + Comedy averages both preferences.
    assert features[2, 2] == 0 and features[2, 4] > 0  # Old like: lifetime only.
    assert features[3, 1] == 0  # No categories: no category match.
    assert small_world == before
    assert np.isfinite(features).all() and np.all((features >= 0) & (features <= 1))


def test_no_history_empty_catalogue_and_no_categories(small_world, model):
    _, features = build_features(small_world, 3, NOW, model)
    assert np.all(features[:, [1, 3]] == 0)
    empty = LearnedSnapshot([], {}, [])
    assert build_features(empty, 3, NOW, model)[1].shape == (0, 6)
    assert rank_learned(empty, 3, NOW, model, 20) == []
    no_categories = LearnedSnapshot(small_world.posts, {}, [])
    _, features = build_features(no_categories, 3, NOW, model)
    assert np.all(features[:, [1, 2, 3, 4]] == 0)


def test_global_counts_include_excluded_posts(small_world, model):
    small_world.posts[4] = small_world.posts[4].model_copy(update={"user_id": 3})
    posts, features = build_features(small_world, 3, NOW, model)
    assert 5 not in [p.id for p in posts]  # Own post still supplies the global maximum of 2.
    assert features[0, 2] == 0.5
    assert features[0, 4] == pytest.approx(np.log1p(1) / np.log1p(2))


def test_liked_post_with_two_categories_contributes_to_both(small_world, model):
    small_world.likes.append(HistoricalLike(7, 6, NOW - timedelta(days=1)))
    posts, features = build_features(small_world, 7, NOW, model)
    assert [post.id for post in posts] == [5, 7, 8]
    # Five liked posts produce six category memberships: four Drama, two Comedy.
    assert features[0, 1] == pytest.approx(4 / 6)


def test_time_window_boundaries_and_future_information(small_world, model):
    small_world.likes = [
        HistoricalLike(1, 1, NOW - timedelta(days=365)),
        HistoricalLike(2, 2, NOW - timedelta(days=365, microseconds=1)),
        HistoricalLike(3, 3, NOW),
        HistoricalLike(4, 4, NOW + timedelta(days=1)),
    ]
    small_world.posts[4] = small_world.posts[4].model_copy(update={"created_at": NOW})
    small_world.posts[5] = small_world.posts[5].model_copy(
        update={"created_at": NOW + timedelta(days=1)}
    )
    posts, features = build_features(small_world, 9, NOW, model)
    assert [p.id for p in posts] == [1, 2, 3, 4, 7, 8]
    assert features[:4, 2].tolist() == [1, 0, 0, 0]
    assert features[:4, 4].tolist() == [1, 1, 0, 0]


def test_signal_caps_and_constants_come_from_model(small_world, model):
    settings = dict(model)
    settings.update(
        half_life_days=np.array(365),
        popularity_days=np.array(1),
        activity_cap=np.array(2),
        age_cap_days=np.array(730),
    )
    _, features = build_features(small_world, 7, NOW, settings)
    assert np.all(features[:, 0] == 0.125)
    assert np.all(features[:, 2] == 0)
    assert np.all(features[:, [3, 5]] == 1)


def test_golden_predictions_are_pure_and_deterministic(model):
    golden = json.loads((Path(__file__).parent / "fixtures/week05-golden.json").read_text())
    assert golden["features"] == FEATURES == model["features"].tolist()
    features = np.array(golden["rows"])
    before = features.copy()
    saved_before = {key: value.copy() for key, value in model.items()}
    scores = predict(model, features)
    np.testing.assert_allclose(
        scores, golden["probabilities"], rtol=0, atol=golden["absolute_tolerance"]
    )
    np.testing.assert_array_equal(scores, predict(model, features))
    np.testing.assert_array_equal(features, before)
    for key in model:
        np.testing.assert_array_equal(model[key], saved_before[key])
        assert not model[key].flags.writeable
    assert predict(model, np.empty((0, 6))).shape == (0,)
    assert np.all((scores >= 0) & (scores <= 1))


def test_top_k_matches_full_sort_and_ties_use_id(small_world, model):
    posts, features = build_features(small_world, 7, NOW, model)
    expected = sorted(zip(posts, predict(model, features)), key=lambda pair: (-pair[1], pair[0].id))
    assert [hit.post.id for hit in rank_learned(small_world, 7, NOW, model, 2)] == [
        post.id for post, _ in expected[:2]
    ]
    tied = dict(model)
    tied["W2"] = np.zeros_like(model["W2"])
    assert [hit.post.id for hit in rank_learned(small_world, 7, NOW, tied, 50)] == [5, 6, 7, 8]
    reversed_world = LearnedSnapshot(
        list(reversed(small_world.posts)), small_world.categories, list(reversed(small_world.likes))
    )
    assert rank_learned(small_world, 7, NOW, model, 3) == rank_learned(
        reversed_world, 7, NOW, model, 3
    )
    assert rank_learned(small_world, 7, NOW, model, 0) == []
    with pytest.raises(ValueError):
        rank_learned(small_world, 7, NOW, model, -1)


@pytest.mark.parametrize("defect", ["missing", "order", "shape", "nan", "sd", "constant"])
def test_invalid_model_rejected(tmp_path, model, defect):
    bad = {key: value.copy() for key, value in model.items()}
    if defect == "missing":
        del bad["W1"]
    elif defect == "order":
        bad["features"] = bad["features"][::-1]
    elif defect == "shape":
        bad["W2"] = np.zeros((1, 1))
    elif defect == "nan":
        bad["mu"][0] = np.nan
    elif defect == "sd":
        bad["sd"][0] = 0
    else:
        bad["activity_cap"] = np.array(-1)
    path = tmp_path / "invalid.npz"
    np.savez(path, **bad)
    with pytest.raises(LearnedUnavailable):
        load_model(path)


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / "week05.db"
    seed_demo(path, NOW)
    monkeypatch.setenv("INSTAKILL_DB_PATH", str(path))

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr("app.api.discovery.datetime", FixedDateTime)
    return path


def test_repository_strict_cutoff_and_single_snapshot_data(database, model):
    repository = SQLitePostRepository(database)
    before = FeedService(repository, like_model=model).build(1, NOW, "learned")
    assert repository.learned_snapshot(999, NOW) is None
    with closing(get_connection(database)) as conn, conn:
        conn.execute('INSERT INTO "like" VALUES(1,7,?)', (NOW.isoformat(),))
        conn.execute('INSERT INTO "like" VALUES(1,8,?)', ((NOW + timedelta(days=1)).isoformat(),))
        for post_id, stamp in [(31, NOW), (32, NOW + timedelta(days=1))]:
            conn.execute(
                "INSERT INTO post VALUES(?,2,'Not yet visible',?)", (post_id, stamp.isoformat())
            )
            conn.execute("INSERT INTO post_category VALUES(?,'future category')", (post_id,))
        conn.execute("INSERT INTO follow VALUES(1,5,?)", ((NOW - timedelta(days=1)).isoformat(),))
    assert before == FeedService(repository, like_model=model).build(1, NOW, "learned")
    snapshot = repository.learned_snapshot(1, NOW)
    assert all(like.created_at < NOW for like in snapshot.likes)
    assert 31 not in snapshot.categories and 32 not in snapshot.categories


def test_learned_api_and_cold_start(database):
    with TestClient(create_app()) as client:
        response = client.get("/feed?user_id=1&strategy=learned&limit=50")
        assert response.status_code == 200
        body = response.json()
        assert body["strategy"] == "learned"
        posts = body["posts"]
        assert len(posts) == 27
        assert not {14, 19, 30} & {post["post_id"] for post in posts}
        assert all(0 <= post["score"] <= 1 for post in posts)
        assert posts == sorted(posts, key=lambda p: (-p["score"], p["post_id"]))
        assert len(client.get("/feed?user_id=1&strategy=learned&limit=1").json()["posts"]) == 1
        assert client.get("/feed?user_id=999&strategy=learned").status_code == 404
        for query in ("user_id=0", "user_id=1&limit=51", "user_id=1&limit=0", "user_id=x"):
            assert client.get("/feed?strategy=learned&" + query).status_code == 422
        with closing(get_connection(database)) as conn, conn:
            conn.execute("INSERT INTO user(id,username) VALUES(7,'newcomer')")
        assert client.get("/feed?user_id=7&strategy=learned").json()["posts"]
        with closing(get_connection(database)) as conn, conn:
            conn.execute('DELETE FROM "like"')
            conn.execute("DELETE FROM post")
        assert client.get("/feed?user_id=1&strategy=learned").json()["posts"] == []


@pytest.mark.parametrize("missing", [True, False])
def test_model_failure_does_not_break_other_strategies(database, tmp_path, missing):
    path = tmp_path / "unavailable.npz"
    if not missing:
        path.write_bytes(b"not an npz file")
    with TestClient(create_app(like_model_path=path)) as client:
        response = client.get("/feed?user_id=1&strategy=learned")
        assert response.status_code == 503
        assert "For you or Latest" in response.json()["detail"]
        for strategy in ("for_you", "chronological"):
            assert client.get(f"/feed?user_id=1&strategy={strategy}").status_code == 200
        assert client.get("/health").status_code == 200
        assert client.get("/search?q=Python&mode=keyword").status_code == 200


def test_model_is_loaded_once_per_app(database, monkeypatch):
    from app import main

    calls = []

    def counted_load(path):
        calls.append(path)
        return load_model(path)

    monkeypatch.setattr(main, "load_model", counted_load)
    with TestClient(main.create_app()) as client:
        for _ in range(3):
            assert client.get("/feed?user_id=1&strategy=learned").status_code == 200
    assert calls == [MODEL_PATH]


def test_schema_upgrade_preserves_existing_data(database):
    with closing(get_connection(database)) as conn, conn:
        posts = conn.execute("SELECT * FROM post ORDER BY id").fetchall()
        conn.execute("DROP TABLE post_category")  # Simulate a Week 4 database.
    init_db(database)
    init_db(database)
    with closing(get_connection(database)) as conn:
        assert conn.execute("SELECT * FROM post ORDER BY id").fetchall() == posts
        assert conn.execute("SELECT count(*) FROM post_category").fetchone()[0] == 0
