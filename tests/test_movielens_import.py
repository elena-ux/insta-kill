"""MovieLens mapping, preservation, and the historical demo clock."""

from contextlib import closing
from datetime import UTC, datetime
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app.application.feed import FeedService
from app.db.database import get_connection
from app.db.repository import SQLitePostRepository
from app.infrastructure.like_model import load_model
from app.main import create_app
from scripts.seed_db import import_movielens, setup_demo


@pytest.fixture
def source(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "movies.csv").write_text(
        'movieId,title,genres\n10,"Film, A",Drama|Comedy\n20,Film B,(no genres listed)\n'
        "30,Film C,Drama\n40,Unrated film,Action\n"
    )
    (source / "ratings.csv").write_text(
        "userId,movieId,rating,timestamp\n"
        "1,10,3.5,1000000000\n2,10,4.0,1000000100\n"
        "1,20,5.0,1000000200\n2,30,4.5,1000000300\n3,20,2.0,1000000400\n"
    )
    return source


def test_import_preserves_notebook_mapping_and_existing_database(source, tmp_path):
    path = tmp_path / "movies.db"
    info = import_movielens(source, path)
    assert (info["posts"], info["users"], info["likes"]) == (3, 3, 3)
    with closing(get_connection(path)) as conn:
        posts = [tuple(row) for row in conn.execute("SELECT * FROM post ORDER BY id")]
        assert posts == [
            (10, 4, "Film, A", "2001-09-09T01:46:40+00:00"),
            (20, 4, "Film B", "2001-09-09T01:50:00+00:00"),
            (30, 4, "Film C", "2001-09-09T01:51:40+00:00"),
        ]
        assert [tuple(row) for row in conn.execute('SELECT user_id,post_id FROM "like"')] == [
            (1, 20),
            (2, 10),
            (2, 30),
        ]
        assert [tuple(row) for row in conn.execute("SELECT * FROM post_category ORDER BY 1,2")] == [
            (10, "Comedy"),
            (10, "Drama"),
            (30, "Drama"),
        ]
        assert conn.execute("SELECT count(*) FROM follow").fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    before = path.read_bytes()
    with pytest.raises(ValueError, match="never overwritten"):
        import_movielens(source, path)
    assert before == path.read_bytes()


def test_original_zip_and_directory_produce_same_data(source, tmp_path):
    archive = tmp_path / "movies.zip"
    with ZipFile(archive, "w") as z:
        for path in source.iterdir():
            z.write(path, "ml-latest-small/" + path.name)
    paths = [tmp_path / "directory.db", tmp_path / "archive.db"]
    assert import_movielens(source, paths[0]) == import_movielens(archive, paths[1])
    with closing(get_connection(paths[0])) as first, closing(get_connection(paths[1])) as second:
        assert list(first.iterdump()) == list(second.iterdump())


def test_duplicate_ratings_fail_before_database_creation(source, tmp_path):
    with (source / "ratings.csv").open("a") as f:
        f.write("1,10,5.0,1000000500\n")
    path = tmp_path / "invalid.db"
    with pytest.raises(ValueError, match="Duplicate"):
        import_movielens(source, path)
    assert not path.exists()


def test_feed_uses_visible_historical_clock_for_all_strategies(source, tmp_path, monkeypatch):
    path = tmp_path / "movies.db"
    info = import_movielens(source, path)
    monkeypatch.setenv("INSTAKILL_DB_PATH", str(path))
    service = FeedService(SQLitePostRepository(path), like_model=load_model())
    reference_time = datetime.fromisoformat(info["reference_time"])
    assert reference_time == datetime.fromtimestamp(1000000401, UTC)
    with TestClient(create_app()) as client:
        dataset = client.get("/dataset").json()
        assert dataset["source"] == "movielens"
        assert dataset["reference_time"] == info["reference_time"]
        assert (dataset["first_user_id"], dataset["last_user_id"]) == (1, 3)
        for strategy in ("learned", "for_you", "chronological"):
            response = client.get(f"/feed?user_id=1&strategy={strategy}&limit=20")
            expected = service.build(1, reference_time, strategy).model_dump(
                mode="json", exclude_none=True
            )
            assert response.status_code == 200 and response.json() == expected
        cold = client.get("/feed?user_id=3&strategy=learned").json()
        assert len(cold["posts"]) == 3  # Low ratings are not likes.


def test_one_database_keeps_collections_and_normalization_separate(source, tmp_path, monkeypatch):
    path = tmp_path / "instakill.db"
    setup_demo(source, path)
    before = path.read_bytes()
    setup_demo(source, path)
    assert path.read_bytes() == before  # Re-running setup preserves existing data.
    monkeypatch.setenv("INSTAKILL_DB_PATH", str(path))
    with TestClient(create_app()) as client:
        info = client.get("/dataset").json()
        assert info["default_collection"] == "community"
        assert info["collections"]["movies"]["posts"] == 3
        assert info["collections"]["community"]["posts"] == 36
        assert info["collections"]["movies"]["catalogue_user_id"] == 4
        assert info["collections"]["movies"]["reference_time"] is not None
        community_info = client.get("/dataset?collection=community").json()
        assert community_info == info["collections"]["community"]
        assert community_info["catalogue_user_id"] is None
        assert community_info["reference_time"] is None
        movies = client.get("/feed?user_id=1&strategy=learned&collection=movies").json()
        assert {post["post_id"] for post in movies["posts"]} == {10, 30}
        community_id = info["collections"]["community"]["first_user_id"]
        community = client.get(f"/feed?user_id={community_id}&collection=community").json()
        assert all(post["post_id"] > 30 for post in community["posts"])
        assert client.get("/search?q=Python&mode=keyword&collection=movies").json()["results"] == []
        assert client.get("/search?q=Python&mode=keyword&collection=community").json()["results"]
        assert client.get("/feed?user_id=1&collection=invalid").status_code == 422
        with closing(get_connection(path)) as conn, conn:
            # Community likes must not change the MovieLens global denominator.
            conn.execute("UPDATE post SET created_at='2000-01-01T00:00:00+00:00' WHERE id=31")
            conn.executemany(
                'INSERT INTO "like" VALUES(?,31,?)',
                [(user, "2001-01-01T00:00:00+00:00") for user in (1, 2, 3)],
            )
        assert client.get("/feed?user_id=1&strategy=learned&collection=movies").json() == movies


def test_draft_preview_uses_existing_service_without_saving(source, tmp_path, monkeypatch):
    path = tmp_path / "instakill.db"
    setup_demo(source, path)
    monkeypatch.setenv("INSTAKILL_DB_PATH", str(path))
    with TestClient(create_app()) as client:
        before = client.get("/dataset").json()["posts"]
        response = client.post("/posts/preview", json={"user_id": 1, "content": "  Hello  \n"})
        assert response.status_code == 200
        assert response.json() == {"id": None, "user_id": 1, "content": "Hello", "created_at": None}
        assert client.get("/dataset").json()["posts"] == before
        assert (
            client.post("/posts/preview", json={"user_id": 1, "content": " \n "}).status_code == 422
        )
        assert (
            client.post("/posts/preview", json={"user_id": 999, "content": "Hi"}).status_code == 404
        )
