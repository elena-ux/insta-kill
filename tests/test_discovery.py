from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api.discovery import search_service
from app.application.search import SearchService
from app.db.database import get_connection
from app.db.repository import SQLitePostRepository
from app.infrastructure.encoder import SearchUnavailable
from app.main import create_app
from scripts.seed_db import seed_demo

NOW = datetime(2026, 10, 26, 16, 0, tzinfo=UTC)


class FakeEncoder:
    def __init__(self):
        self.calls = []

    def encode(self, texts):
        self.calls.append(list(texts))
        return np.array(
            [[1.0, 0.0] if "Python" in t or "types" in t else [0.0, 1.0] for t in texts]
        )


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / "demo.db"
    seed_demo(path, NOW)
    monkeypatch.setenv("INSTAKILL_DB_PATH", str(path))
    return path


def test_search_uses_current_posts_after_insert_edit_and_delete(database):
    repo = SQLitePostRepository(database)
    encoder = FakeEncoder()
    service = SearchService(repo, encoder)
    first = service.search("types")
    assert first.results[0].post.id == 11
    service.search("types")
    with closing(get_connection(database)) as c, c:
        c.execute("INSERT INTO post(id,user_id,content) VALUES(31,2,'Python types new')")
    assert 31 in [h.post.id for h in service.search("types", limit=50).results]
    with closing(get_connection(database)) as c, c:
        c.execute("UPDATE post SET content='tomato soup' WHERE id=11")
    assert service.search("types").results[0].post.id == 12
    with closing(get_connection(database)) as c, c:
        c.execute("DELETE FROM post WHERE id=31")
    assert 31 not in [h.post.id for h in service.search("types", limit=50).results]


def test_keyword_baseline_and_empty_database(database):
    encoder = FakeEncoder()
    repo = SQLitePostRepository(database)
    service = SearchService(repo, encoder)
    assert service.search("quantum scholarship", "keyword").results == []
    hits = service.search("Python types", "keyword").results
    assert hits[0].post.id == 11 and hits[0].score == 1
    assert not encoder.calls
    with closing(get_connection(database)) as c, c:
        c.execute("DELETE FROM post")
    assert service.search("types").results == [] and not encoder.calls


def test_concurrent_requests_return_same_results(database):
    encoder = FakeEncoder()
    service = SearchService(SQLitePostRepository(database), encoder)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.search("types"), range(8)))
    assert all(r.results[0].post.id == 11 for r in results)


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"q": "   "},
        {"q": "a" * 501},
        {"q": "x", "limit": 0},
        {"q": "x", "limit": 51},
        {"q": "x", "mode": "other"},
        {"q": "x", "limit": "abc"},
    ],
)
def test_search_validation(database, params):
    with TestClient(create_app()) as client:
        assert client.get("/search", params=params).status_code == 422


def test_search_api_and_recoverable_encoder_failure(database):
    class BrokenEncoder:
        def encode(self, texts):
            raise SearchUnavailable("offline")

    app = create_app()
    app.dependency_overrides[search_service] = lambda: SearchService(
        SQLitePostRepository(database), BrokenEncoder()
    )
    with TestClient(app) as client:
        assert client.get("/search", params={"q": "types"}).status_code == 503
        response = client.get("/search", params={"q": "Python", "mode": "keyword", "limit": 2})
        assert response.status_code == 200 and len(response.json()["results"]) == 2
        assert client.get("/health").json() == {"status": "ok"}
        assert client.post("/posts/preview").status_code == 404


def test_demo_refuses_existing_database(database):
    before = database.read_bytes()
    with pytest.raises(ValueError):
        seed_demo(database, NOW)
    assert database.read_bytes() == before
