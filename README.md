# InstaKill

Programming for AI · Elena Podariu-Ungureanu

One application for preparing drafts, searching posts, and comparing feed strategies.
It uses a single SQLite database, `data/instakill.db`, with **Community** and **Movies**
collections. Change the collection in the page; the server and database stay the same.

## Running the app

Python 3.11+; tested with Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m scripts.seed_db --source "../week04/ml-latest-small (1).zip"
npm --prefix frontend ci
npm --prefix frontend run build
uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Use your local MovieLens ZIP or a directory containing `movies.csv` and `ratings.csv`.
Setup creates the database once and reuses it on later runs. Start only the last
command when returning to the app. No database environment variable is needed.

Open [InstaKill](http://127.0.0.1:8010/search/) or [the API](http://127.0.0.1:8010/docs).
MovieLens data stays local. The learned model is packaged with the app; semantic
search downloads its pretrained CPU encoder on first use if it is not cached.

## Trying the concepts together

| Concept | Where to try it |
| --- | --- |
| Week 1: FastAPI, Pydantic and the service boundary | `/health`, the connection status, and typed request/response validation |
| Week 2: preparing a draft without database effects | **Draft**: enter text, preview the trimmed result, and try blank input |
| Week 3: embeddings, NumPy cosine similarity and deterministic top-k | **Discover**: compare **By meaning** with **By words** |
| Week 4: follows, freshness, popularity and heap selection | **Community → Your feed**: compare **For you** with **Latest** |
| Week 5: six signals, saved standardization and NumPy inference | **Movies → Your feed → Learned**: compare users 1, 414 and 442 |

Community includes the 30 classroom examples and six original starter posts.
Its first member follows two authors and has two likes; the sixth follows nobody.
The page shows the available user IDs. MovieLens keeps all 9,724 rated films,
610 users and 48,580 likes. Its catalogue author is separate from those users.
Each collection supplies its own candidates and normalization counts.
In MovieLens, film titles become posts, genres become categories, and ratings of
4 or more become likes. A film appears at its first rating, as in the notebook.
The source timestamps are preserved. MovieLens latest-small is provided by
GroupLens; its archive includes the dataset's terms of use.

Drafts are previews, so they do not modify either collection. Training and
backpropagation remain in the completed notebook; the application uses the saved model.

## Checks

```bash
python -m pytest -q
ruff check .
npm --prefix frontend run check
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

Browser tests use the application running on port 8010. Set
`PLAYWRIGHT_CHROMIUM_EXECUTABLE` if using an installed browser instead of Playwright's.
Temporary unit-test databases are isolated and never replace the application database.

To verify MovieLens signals and predictions against the completed notebook:

```bash
python -m scripts.verify_movielens --source "../week04/ml-latest-small (1).zip" --database data/instakill.db --notebook "../week05/week05_(1).ipynb" --output docs/evidence/unified/movielens-verification.json
```

The script reads only inference definitions; it does not train or export a model.
Search examples, the prediction benchmark, and earlier verification outputs remain
available for revision alongside the [API contract](docs/api-contract.md).

I checked the formulas on small examples with known answers, then compared the
MovieLens signals and predictions with the notebook. All 94,815 compared rows
matched. Another test adds community likes and checks that the MovieLens feed
stays unchanged, so sharing a database does not mix the calculations.

The browser tests check the same steps used in the app: searching, changing the
collection and feed strategy, and previewing a draft. Displayed results must match
the API, and a preview must leave the post count unchanged. These checks support
the integration; recommendation quality on real social posts still needs separate
evaluation. [Verification results](docs/evidence/unified/checks.json).

## Submitted weekly explanations

The weekly explanations are retained:
[Week 2](docs/week02.md) · [Week 3](docs/week03.md) ·
[Week 4](docs/week04.md) · [Week 5](docs/week05.md).
Earlier setup commands in these records refer to the separate demos used at that stage.
Use the single setup above for the current application.

## Feed — Week 5

`GET /feed?user_id=1&limit=20&strategy=learned&collection=movies` uses the exported
model. `for_you` remains the default strategy. Collection selection does not change
the model, its formulas, or the saved input scaling.

## Feed — Week 4

`GET /feed?user_id=612&limit=20&strategy=for_you&collection=community` returns
posts ordered by score for the first seeded Community member.
With `strategy=chronological`, posts are ordered newest first.
The Community collection includes the seeded follows and likes.
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
