# API

## Implemented

| Request | Response |
| --- | --- |
| `GET /health` | `{"status":"ok"}` |
| `GET /dataset` | Overall counts, `default_collection`, and `collections` with counts and source information |
| `POST /posts/preview` | Unsaved `{id: null, user_id, content, created_at: null}` |
| `GET /search?q=...&limit=5&mode=semantic` | `{query, mode, results: [{post, score}]}` |
| `GET /feed?user_id=612&limit=20&strategy=for_you&collection=community` | `{user_id, strategy, posts: [{post_id, user_id, content, created_at, score}]}` |

For search, `q` is required, must not be blank, and has a maximum of 500 characters.
`limit` is between 1 and 50. `mode` is `semantic` or `keyword`.
Invalid parameters return `422`; model unavailability returns `503`.

Search and feed accept `collection=community|movies`. The unified app defaults
to `community`; a legacy MovieLens-only database defaults to `movies`.
Both collections share `data/instakill.db`. Candidates, category history and global
normalization counts stay within the selected collection.
`GET /dataset?collection=movies` or `community` returns that collection's counts.

`POST /posts/preview` accepts `{"user_id": 612, "content": " A draft. "}`.
It uses the Week 2 service to trim the text and validate the author. The author
must exist (`404` otherwise); blank content, invalid IDs or more than 5,000 characters
return `422`. The result is not saved, published, or added to search and feed results.

## `GET /feed`

- `user_id`: required positive integer.
- `limit`: integer between 1 and 50, default 20.
- `strategy`: `for_you`, `chronological`, or `learned`, default `for_you`.
- `collection`: `community` or `movies`; see the default above.

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

The MovieLens collection uses a fixed historical reference time stored by the
importer: one second after the last rating. This applies to all three strategies
as an internal calculation setting. `GET /dataset` reports that time and actual row counts;
`users` excludes the separate catalogue author. For the Community collection,
`reference_time` and `catalogue_user_id` are null and feeds use the current UTC time.
The feed response structure is unchanged.

An unknown user returns `404`. A missing `user_id`, a nonpositive ID, an invalid
type, an out-of-range limit, or an unknown strategy returns `422`, with
validation details in `detail`.

If the packaged model is missing or invalid, `learned` returns `503` with
`{"detail": "Learned feed is unavailable. Try For you or Latest."}`.
The other strategies, keyword search and health endpoint continue to work.
