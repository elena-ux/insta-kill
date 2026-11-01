# Week 4 — Feed (local)

The feed uses three small functions:

- `freshness`: starts at 1 and halves every 72 hours.
- `affinity`: 1 for a followed author, 0 otherwise.
- `popularity`: the post's likes up to `now`, divided by the maximum per-post
  like count in the database at the same time; 0 if there are no likes.

`score = freshness + 2 × affinity + popularity`

The default weights are `(1, 2, 1)`. Giving `affinity` a weight of 2 prioritizes
followed authors as an explicit user preference. Freshness and popularity have
equal weights and distinguish posts within each group. These are initial choices;
their recommendation quality has not been measured.

Candidates are all posts that exist by `now`, including posts by unfollowed
authors, excluding the user's own posts and posts they have already liked by
that time. Future follows and likes are ignored.
A user who follows nobody gets the same eligibility rules, with `affinity = 0`;
the personalized order then depends on freshness and popularity.

`rank_feed(candidates, signals, now, weights, limit)` uses a heap to select posts
by score descending, then ID ascending. It does not read the database or clock
and does not mutate its inputs. The repository reads data, `FeedService` builds
the signals, and the API validates the request and formats the response.
The chronological option uses the same candidates, ordered newest first.

Tests: `python -m pytest`. They check ordering, ties, determinism, unchanged
inputs, and the endpoint against the seeded database.
Request complexity and the repeated work suitable for precomputation are described in the
[README](../README.md#feed--week-4); parameters and errors are in the
[API contract](api-contract.md#get-feed).

UI: `cd frontend`, `npm ci`, `npm run build`. Start the backend with the demo
database on port 8010 and open `http://127.0.0.1:8010/search/`.
