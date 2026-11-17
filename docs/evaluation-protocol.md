# Week 7 — Offline feed evaluation

Programming for AI · Elena Podariu-Ungureanu · 17 November 2026

**Question.** Which feed puts a user's later likes near the top? I compare
`chronological`, `popularity`, `for_you` and `learned` without changing their
ranking rules or the saved model.

**Cut-off and snapshot.** `T` is the 80th percentile of like timestamps. The script
copies the database, then removes records at or after `T` from the copy, including
dependent rows, and resets its clock. The source stays read-only. MovieLens has no
follows; Community follows are fixed examples independent of likes. Titles and
categories are treated as known when a post appears. Dates use UTC.

**Users.** Each user needs at least three likes before `T` and one later like on
a snapshot post. Each user has equal weight. Likes exactly at `T` are excluded
from both periods. The default run includes 25 users.

**Candidates.** Each strategy calls the existing `FeedService.build` with `now=T`
and `limit=10`, as `/feed` does. It ranks all snapshot posts except the user's own
and already-liked posts. The snapshot contains 7,816 MovieLens posts; Community
posts are newer than `T`.

**Relevance.** Relevant posts are snapshot posts the user liked after `T`: 450
user/post pairs in this run. Posts created later are excluded. A missing like
counts as zero relevance, not proof of dislike.

**Metric.** NDCG@10 rewards relevant posts near the top. At zero-based position
`i`, a relevant post contributes `1 / log2(i + 2)`. Divide the sum by the score
of a perfect ranking with up to ten relevant posts first, then average over users.
Scores range from 0 to 1; one relevant post at position 3 scores 0.5. These scores
are not comparable with the lab's one hidden like among 99 random items.

**Intervals.** With seed 42, I resample users with replacement 5,000 times, keeping
their four strategy scores together. The 2.5th and 97.5th percentiles give 95%
intervals. Each slice's highest-mean baseline is held fixed for the paired
`learned - baseline` comparison. An interval above zero means `wins`, below means
`loses`, otherwise `unclear`. Baseline selection and multiple comparisons are not
adjusted for, so slice conclusions are exploratory.

**Slices.** Earlier likes define new `<10`, casual `10–49`, regular `50–199` and
power `200+` users: 1, 10, 7 and 7 respectively. Empty groups have no estimate;
a one-user bootstrap interval cannot describe population uncertainty.

**Model limitation.** Of the 450 evaluation likes, 0 fall in the training period
and 63 (14%) in validation, using the dates and model hash recorded in
[evaluation-model.json](evaluation-model.json). These are period overlaps, not
exact reused examples; validation reuse and the notebook's full-history negative
sampling can make learned performance optimistic.

**Population limitation.** MovieLens records ratings across years, with one
catalogue author and no follows, so it does not test social author affinity well.
No eligible user has a relevant post at most seven days old at `T`; these data
cannot establish which strategy wins on a fresh social feed.

## Result

Learned scores **0.153032**, versus **0.098333** for popularity. Their difference
is **+0.054700**, with interval **[-0.015271, +0.137110]**: **unclear** overall.
The casual slice favours learned; the single new user favours popularity.

[Baseline table](../reports/baseline_table.md) · [Per-user scores](../reports/eval_results.csv) ·
[Dashboard with three charts](../reports/dashboard.html), opened directly in a browser.

## Run and reproduce

From the repository root, with the virtual environment active:

```bash
python -m pip install -e '.[dev,eval]' -c requirements-tested.txt -c requirements-eval-tested.txt
python scripts/evaluate.py
python -m pytest -q
ruff check .
```

The default database is `data/instakill.db` or `INSTAKILL_DB_PATH`.
Options: `--db`, `--cutoff` (ISO date), `--seed` and `--out`.
Pandas and matplotlib are optional evaluation dependencies.

For exact reproduction from a fresh Git clone, use the same MovieLens archive
and fixed Community seed time. Keep the archive and database uncommitted:

```bash
python -m scripts.seed_db --source /path/to/ml-latest-small.zip --database data/week07-replay.db --now 2026-11-08T20:52:27.160011+00:00
python scripts/evaluate.py --db data/week07-replay.db --out /tmp/instakill-week07-reports
cmp reports/eval_results.csv /tmp/instakill-week07-reports/eval_results.csv
cmp reports/baseline_table.md /tmp/instakill-week07-reports/baseline_table.md
```

Choose a new database path. Silent `cmp` output means identical files. The archive
hash is in `evaluation-model.json`. Reports hash database rows independently of
file layout and record the last `app/` commit, plus evaluator and model hashes.

For revision, follow [evaluate.py](../scripts/evaluate.py): `build_snapshot` →
`replay` → `summarize` → `write_reports`. [Tests](../tests/test_evaluate.py) check
known scores, leakage, service reuse, paired intervals and reproducibility on
temporary databases.
