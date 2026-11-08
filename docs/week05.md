# Week 5 — Learn the Scorer

I added `strategy=learned` to `GET /feed`, using the model trained in the
Week 5 notebook. It estimates how likely a user is to like each post and
returns the posts with the highest scores.

The model uses six signals: `freshness`, `affinity`, `popularity`, `activity`,
`lifetime`, and `age`. I kept the notebook's formulas, constants, signal order,
and input scaling.

- [`build_features`](../app/learned.py) calculates the signals from posts, categories, and earlier likes.
- `predict` loads no data itself. It uses the saved weights to calculate probabilities with NumPy on CPU.
- `rank_learned` selects the top results with a heap, breaking score ties by ascending post ID.

Post categories replace movie genres when calculating affinity. For example,
if a user liked three Drama posts and one Comedy post, a Drama candidate has
affinity `3 / 4 = 0.75`. A post without categories has affinity zero.

Own posts and already-liked posts are excluded. Only posts and likes before
the request time are used. Users with no likes have zero affinity and activity.
`for_you` keeps the Week 4 formula, and `chronological` keeps newest-first order.

The model is loaded once when the app starts. If it cannot be loaded, `learned`
returns `503`; the other strategies remain available.

Tests: `python -m pytest`. They check the signal calculations, the notebook's
reference predictions, ordering, ties, exclusions, and API responses. Browser
tests cover the Learned option on desktop and mobile.

Prediction time, using the median of five runs after one warm-up:

| Candidates | Time |
| ---: | ---: |
| 1,000 | 0.084 ms |
| 10,000 | 0.708 ms |
| 100,000 | 7.393 ms |

These timings cover input scaling and prediction.
[Benchmark script](../scripts/benchmark_learned.py) · [Results](week05-benchmark.json).

Prediction costs `O(C × 6 × H)`, where `C` is the number of candidates and `H`
the number of hidden neurons. Selecting the top `k` costs `O(C log k)` for
`k > 1`. Database reads and signal calculation also depend on the post catalogue,
categories, and like history.

The model was evaluated on MovieLens. The synthetic post demo checks the
integration; recommendation quality on real social posts has not been measured.

To try it, follow the [startup instructions](../README.md#feed--week-5) and choose
**Your feed → Learned**. [API example](week05-feed-example.json).
