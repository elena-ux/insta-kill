# Week 7 — Feed evaluation

## Run metadata

- Cut-off (UTC): `2016-02-04T21:38:14+00:00`
- Seed: `42`
- Bootstrap resamples: `5000`
- Eligible users: `25`
- Snapshot posts: `7816`
- Likes before T: `38883`
- Likes exactly at T (excluded): `0`
- Evaluated later likes: `450`
- Database SHA-256 (logical rows): `75dc4ddceb8dbc2ead7cba0416e1903d3be1c73ada7029d51098bb1fed520e54`
- Git commit (last change to app/): `175e3d6c671484d9467b19963e03dc989f360d43`
- Evaluator SHA-256: `e0c5804e9191723f8e3d54d46108fb7245f183f99a9adefa485a96a1e7f17f33`
- Model SHA-256: `32885360b73503766e41356aa0502e6391a6ed5c17f21bc9a9d8ba298cbddebc`
- Users with relevant posts at most 7 days old at T: `0`

## Baselines

| Strategy | Mean NDCG@10 | 95% interval | Users |
| --- | --- | --- | --- |
| chronological | 0.000000 | [0.000000, 0.000000] | 25 |
| popularity | 0.098333 | [0.027368, 0.190465] | 25 |
| for_you | 0.074760 | [0.018599, 0.146486] | 25 |
| learned | 0.153032 | [0.075495, 0.244917] | 25 |

## Learned minus best baseline

| Slice | Best baseline | Learned - baseline | 95% interval | Users | Verdict |
| --- | --- | --- | --- | --- | --- |
| overall | popularity | +0.054700 | [-0.015271, +0.137110] | 25 | unclear |
| new (<10 likes) | popularity | -0.397591 | [-0.397591, -0.397591] | 1 | loses |
| casual (10-49) | popularity | +0.094772 | [+0.011494, +0.197415] | 10 | wins |
| regular (50-199) | popularity | -0.001124 | [-0.034813, +0.031442] | 7 | unclear |
| power (200+) | popularity | +0.117890 | [-0.001124, +0.323914] | 7 | unclear |

## Interpretation limits

Of 450 evaluated later likes, 450 are MovieLens: 0 fall in the training period (before 2013-03-19T09:55:48+00:00); 63 fall in the validation period (before 2016-07-10T02:36:29+00:00). These are period overlaps, not exact reused examples. Validation reuse and full-history negative sampling can make learned performance optimistic.

Each slice uses its best observed baseline, held fixed during bootstrap. Intervals do not adjust for baseline selection or multiple comparisons. Empty groups are n/a; a one-user interval cannot describe population uncertainty. MovieLens results do not establish a winner for fresh social posts and are not comparable with the lab's one-like-among-100-candidates scores.
