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
- `strategy`: `for_you` or `chronological`, default `for_you`.

The `200` response contains `user_id`, `strategy`, and `posts`, with at most
`limit` posts. Each post has `post_id`, `user_id` (the author), `content`, and
`created_at`. For `for_you`, it also includes a numeric `score`; for
`chronological`, the `score` field is omitted.

`for_you` orders by score descending; `chronological` orders by `created_at`
descending. Both break ties by ascending `post_id`.
Own, already-liked, and future posts are excluded from both strategies.
If no posts are eligible, `posts` is an empty list.

An unknown user returns `404`. A missing `user_id`, a nonpositive ID, an invalid
type, an out-of-range limit, or an unknown strategy returns `422`, with
validation details in `detail`.
