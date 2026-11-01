# InstaKill

Programming for AI · Elena Podariu-Ungureanu · 26 October 2026

A social app built with FastAPI and SQLite.

- [Week 2](docs/week02.md): preparing a post draft.
- [Week 3](docs/week03.md): semantic and keyword search.
- [Week 4](docs/week04.md): personalized and chronological feeds.
- [API contract](docs/api-contract.md): requests, responses, and errors.

## Running the app

Python 3.11+; tested with Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m scripts.seed_db --demo data/demo.db
INSTAKILL_DB_PATH="$PWD/data/demo.db" uvicorn app.main:app --reload
```

API: `http://127.0.0.1:8000/docs`. Tests: `python -m pytest`.
The seed creates a new database with synthetic data and refuses to overwrite it.
The first semantic search downloads the CPU model if it is not already cached locally.

## Feed — Week 4

`GET /feed?user_id=1&limit=20&strategy=for_you` returns posts ordered by score.
With `strategy=chronological`, posts are ordered newest first.
The demo seed includes follows and likes; user 6 follows nobody.
The feed can be tried from `/docs` without the frontend.

For `C` candidates and limit `k`, scoring costs O(C) and heap selection costs
O(C log k) for k > 1; for k = 1, it is O(C).
The chronological strategy also uses a heap, with timestamps instead of scores.
A request also includes SQLite reads: filtering posts, checking the user's likes,
reading followed authors, and counting likes per post. This cost depends on the
database tables and indexes, not just the remaining candidates.
For `for_you`, finding the maximum like count adds O(M), where M is the number
of posts with likes returned by the aggregation. Memory includes O(C) for
candidates and scores, O(M) for counts, and the set of followed authors.

Per-post like counts and their maximum are recalculated for each request.
They are the first precomputation target because they are shared across users
at the same `now`. The current implementation calculates them on demand.
