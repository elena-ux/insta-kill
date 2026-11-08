# API

## Implemented

| Request | Response |
| --- | --- |
| `GET /health` | `{"status":"ok"}` |
| `GET /search?q=...&limit=5&mode=semantic` | `{query, mode, results: [{post, score}]}` |
| `GET /feed?user_id=1&limit=20&strategy=for_you` | `{user_id, strategy, posts: [{post_id, user_id, content, created_at, score}]}` |

For search, `q` is required, must not be blank, and has a maximum of 500 characters.
`limit` is between 1 and 50. `mode` is `semantic` or `keyword`.
Invalid parameters return `422`; model unavailability returns `503`.

## `GET /feed`

- `user_id`: required positive integer.
- `limit`: integer between 1 and 50, default 20.
- `strategy`: `for_you`, `chronological`, or `learned`, default `for_you`.

The `200` response contains `user_id`, `strategy`, and `posts`, with at most
`limit` posts. Each post has `post_id`, `user_id` (the author), `content`, and
`created_at`. For `for_you`, it also includes the numeric formula `score`.
For `learned`, `score` is the model's estimated P(like), between 0 and 1.
For `chronological`, the `score` field is omitted.

`for_you` and `learned` order by score descending; `chronological` orders by
`created_at` descending. All break ties by ascending `post_id`.
Own, already-liked, and future posts are excluded from all strategies.
If no posts are eligible, `posts` is an empty list.

For `learned`, posts and likes must be strictly before the server's UTC request
time. The other strategies keep their Week 4 inclusive cutoff. Learned popularity
includes likes exactly 365 days before the request time. All six signals use the
model's saved constants; follows do not affect learned ranking. No like history
means zero activity and affinity; a post without categories has zero affinity.
See the [captured learned response](week05-feed-example.json).

An unknown user returns `404`. A missing `user_id`, a nonpositive ID, an invalid
type, an out-of-range limit, or an unknown strategy returns `422`, with
validation details in `detail`.

If the packaged model is missing or invalid, `learned` returns `503` with
`{"detail": "Learned feed is unavailable. Try For you or Latest."}`.
The other strategies, keyword search and health endpoint continue to work.
