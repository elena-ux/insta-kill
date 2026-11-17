"""Week 7: replay the existing feed on a temporary, strictly historical database."""

import argparse
import base64
import hashlib
import html
import io
import json
import math
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

# Also support the assignment's direct command: python scripts/evaluate.py.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.application.feed import FeedService
from app.db.database import database_path, get_connection
from app.db.repository import SQLitePostRepository
from app.infrastructure.like_model import MODEL_PATH, load_model
from app.ranking import utc

STRATEGIES = ("chronological", "popularity", "for_you", "learned")
GROUPS = ("new (<10 likes)", "casual (10-49)", "regular (50-199)", "power (200+)")
COLORS = ("#657385", "#ba640b", "#16796e", "#774594")
BOOTSTRAPS = 5000


def parse_time(value: str) -> datetime:
    """Accept ISO dates, treating an omitted timezone as UTC."""
    return utc(datetime.fromisoformat(value))


def ndcg_at_10(ranking: list[int], relevant: set[int]) -> float:
    """Several later likes can be relevant; a perfect ranking has score 1."""
    ideal = sum(1 / math.log2(i + 2) for i in range(min(10, len(relevant))))
    if not ideal:
        return 0.0
    dcg = sum(int(post in relevant) / math.log2(i + 2) for i, post in enumerate(ranking[:10]))
    return dcg / ideal


def user_group(n_likes: int) -> str:
    if n_likes < 10:
        return GROUPS[0]
    if n_likes < 50:
        return GROUPS[1]
    if n_likes < 200:
        return GROUPS[2]
    return GROUPS[3]


def database_fingerprint(conn: sqlite3.Connection) -> str:
    """Hash logical rows, so SQLite page layout does not affect reproduction."""
    digest = hashlib.sha256()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    for (name,) in tables:
        quoted = '"' + name.replace('"', '""') + '"'
        cursor = conn.execute(f"SELECT * FROM {quoted}")
        columns = [column[0] for column in cursor.description]
        rows = sorted(json.dumps(list(row), ensure_ascii=False) for row in cursor)
        digest.update(json.dumps([name, columns, rows], ensure_ascii=False).encode())
    return digest.hexdigest()


def build_snapshot(source: Path, target: Path, cutoff: datetime | None = None):
    """Copy first; retain later likes in memory as answers, then prune only the copy."""
    if target.exists():
        raise ValueError("The temporary snapshot path must be new.")
    # mode=ro also prevents a misspelled source from creating an empty database.
    with (
        closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as original,
        closing(sqlite3.connect(target)) as snapshot,
    ):
        original.backup(snapshot)

    with closing(get_connection(target)) as conn, conn:
        fingerprint = database_fingerprint(conn)
        likes = [dict(row) for row in conn.execute('SELECT * FROM "like" ORDER BY user_id,post_id')]
        if not likes:
            raise ValueError("The database has no likes for a time split.")
        for like in likes:
            like["created_at"] = parse_time(like["created_at"])
        if cutoff is None:
            timestamps = [like["created_at"].timestamp() for like in likes]
            cutoff = datetime.fromtimestamp(float(np.quantile(timestamps, 0.8)), UTC)
        cutoff = utc(cutoff)
        # Compare in Python: preserve timezone offsets and subsecond boundaries.
        conn.create_function("before_cutoff", 1, lambda value: parse_time(value) < cutoff)
        conn.execute('DELETE FROM "like" WHERE NOT before_cutoff(created_at)')
        conn.execute("DELETE FROM follow WHERE NOT before_cutoff(created_at)")
        conn.execute(
            'DELETE FROM "like" WHERE post_id IN '
            "(SELECT id FROM post WHERE NOT before_cutoff(created_at))"
        )
        conn.execute("DELETE FROM post WHERE NOT before_cutoff(created_at)")
        # Later users and the dataset's final clock are not historical input either.
        conn.execute(
            'DELETE FROM "like" WHERE user_id IN '
            "(SELECT id FROM user WHERE NOT before_cutoff(created_at))"
        )
        conn.execute(
            "DELETE FROM follow WHERE follower_id IN "
            "(SELECT id FROM user WHERE NOT before_cutoff(created_at)) "
            "OR followed_id IN (SELECT id FROM user WHERE NOT before_cutoff(created_at))"
        )
        conn.execute("DELETE FROM user WHERE NOT before_cutoff(created_at)")
        conn.execute("UPDATE dataset_info SET reference_time=?", (cutoff.isoformat(),))
        for table in ("user", "post"):
            conn.execute(
                f"UPDATE sqlite_sequence SET seq=(SELECT coalesce(max(id),0) FROM {table}) "
                "WHERE name=?",
                (table,),
            )
        posts = {row["id"]: dict(row) for row in conn.execute("SELECT * FROM post ORDER BY id")}
        counts = dict(conn.execute('SELECT user_id,count(*) FROM "like" GROUP BY user_id'))
        movie_ids = {row[0] for row in conn.execute("SELECT post_id FROM movielens_post")}
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("The snapshot has inconsistent foreign keys.")
    return cutoff, likes, posts, counts, movie_ids, fingerprint


def replay(snapshot: Path, cutoff: datetime, likes: list[dict], posts: dict, counts: dict):
    """One top-10 question per eligible user and strategy, through the real service."""
    relevant = {}
    for like in likes:
        if like["created_at"] > cutoff and like["post_id"] in posts:
            relevant.setdefault(like["user_id"], set()).add(like["post_id"])
    users = sorted(user for user in relevant if counts.get(user, 0) >= 3)
    if not users:
        raise ValueError("No users have 3 earlier likes and a later like on a snapshot post.")
    service = FeedService(SQLitePostRepository(snapshot), like_model=load_model())
    rows, fresh_users = [], set()
    for user in users:
        if any(
            parse_time(posts[p]["created_at"]) >= cutoff - timedelta(days=7) for p in relevant[user]
        ):
            fresh_users.add(user)
        for strategy in STRATEGIES:
            response = service.build(user, now=cutoff, strategy=strategy, limit=10)
            rows.append(
                {
                    "user_id": user,
                    "strategy": strategy,
                    "ndcg_at_10": ndcg_at_10([p.post_id for p in response.posts], relevant[user]),
                    "n_relevant": len(relevant[user]),
                    "user_group": user_group(counts[user]),
                }
            )
    return pd.DataFrame(rows), fresh_users, relevant


def summarize(results: pd.DataFrame, seed: int):
    """Resample users together across all four strategies; keep differences paired."""
    wide = results.pivot(index="user_id", columns="strategy", values="ndcg_at_10")
    wide = wide.reindex(columns=STRATEGIES).sort_index()
    activity = results.drop_duplicates("user_id").set_index("user_id")["user_group"]
    slices = {"overall": wide}
    for group in GROUPS:
        slices[group] = wide.loc[activity.reindex(wide.index) == group]
    summaries, differences = [], []
    rng = np.random.default_rng(seed)
    for name, frame in slices.items():
        values, n = frame.to_numpy(), len(frame)
        if not n:
            differences.append(
                {
                    "slice": name,
                    "baseline": "n/a",
                    "mean": np.nan,
                    "low": np.nan,
                    "high": np.nan,
                    "users": 0,
                    "verdict": "unclear",
                }
            )
            continue
        means = values.mean(axis=0)
        boot = np.empty((BOOTSTRAPS, len(STRATEGIES)))
        for sample in range(BOOTSTRAPS):
            sampled_users = rng.integers(0, n, size=n)
            boot[sample] = values[sampled_users].mean(axis=0)
        low, high = np.quantile(boot, [0.025, 0.975], axis=0)
        for j, strategy in enumerate(STRATEGIES):
            summaries.append(
                {
                    "slice": name,
                    "strategy": strategy,
                    "mean": means[j],
                    "low": low[j],
                    "high": high[j],
                    "users": n,
                }
            )
        # Best observed baseline in this slice; ties use STRATEGIES order.
        best = int(np.argmax(means[:3]))
        paired_differences = boot[:, 3] - boot[:, best]
        delta_low, delta_high = np.quantile(paired_differences, [0.025, 0.975])
        verdict = "unclear"
        if delta_low > 0:
            verdict = "wins"
        elif delta_high < 0:
            verdict = "loses"
        differences.append(
            {
                "slice": name,
                "baseline": STRATEGIES[best],
                "mean": means[3] - means[best],
                "low": delta_low,
                "high": delta_high,
                "users": n,
                "verdict": verdict,
            }
        )
    return pd.DataFrame(summaries), pd.DataFrame(differences)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def model_overlap(
    likes: list[dict], results: pd.DataFrame, posts: dict, movie_ids: set[int], cutoff: datetime
) -> str:
    """Use recorded Week 5 dates only for the matching, unchanged model export."""
    provenance = json.loads((ROOT / "docs/evaluation-model.json").read_text())
    if file_hash(MODEL_PATH) != provenance["model_sha256"]:
        return "Unknown: model hash differs from the documented Week 5 export."
    users = set(results.user_id)
    evaluated = [
        like
        for like in likes
        if like["user_id"] in users and like["post_id"] in posts and like["created_at"] > cutoff
    ]
    movie_likes = [like for like in evaluated if like["post_id"] in movie_ids]
    train_end = parse_time(provenance["train_before"])
    val_end = parse_time(provenance["validation_before"])
    train = sum(like["created_at"] < train_end for like in movie_likes)
    val = sum(train_end <= like["created_at"] < val_end for like in movie_likes)
    return (
        f"Of {len(evaluated)} evaluated later likes, {len(movie_likes)} are MovieLens: "
        f"{train} fall in the training period (before {train_end.isoformat()}); "
        f"{val} fall in the validation period (before {val_end.isoformat()}). "
        "These are period overlaps, not exact reused examples. Validation reuse and "
        "full-history negative sampling can make learned performance optimistic."
    )


def run_metadata(cutoff, likes, posts, results, fingerprint, seed):
    # HEAD would change when reports are committed, breaking exact reproduction.
    # Record the last product-code commit and hash the evaluator separately.
    commit = (
        subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", "app"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        or "unavailable (not a git clone)"
    )
    return {
        "Cut-off (UTC)": cutoff.isoformat(),
        "Seed": seed,
        "Bootstrap resamples": BOOTSTRAPS,
        "Eligible users": results.user_id.nunique(),
        "Snapshot posts": len(posts),
        "Likes before T": sum(l["created_at"] < cutoff for l in likes),
        "Likes exactly at T (excluded)": sum(l["created_at"] == cutoff for l in likes),
        "Evaluated later likes": int(results.drop_duplicates("user_id").n_relevant.sum()),
        "Database SHA-256 (logical rows)": fingerprint,
        "Git commit (last change to app/)": commit,
        "Evaluator SHA-256": file_hash(Path(__file__)),
        "Model SHA-256": file_hash(MODEL_PATH),
    }


def display_tables(summaries, differences):
    baseline = summaries[summaries["slice"] == "overall"]
    overall_rows = [
        [r.strategy, f"{r.mean:.6f}", f"[{r.low:.6f}, {r.high:.6f}]", str(r.users)]
        for r in baseline.itertuples()
    ]
    delta_rows = [
        [
            r.slice,
            r.baseline,
            f"{r.mean:+.6f}" if r.users else "n/a",
            f"[{r.low:+.6f}, {r.high:+.6f}]" if r.users else "n/a",
            str(r.users),
            r.verdict,
        ]
        for r in differences.itertuples()
    ]
    return [
        (["Strategy", "Mean NDCG@10", "95% interval", "Users"], overall_rows),
        (
            ["Slice", "Best baseline", "Learned - baseline", "95% interval", "Users", "Verdict"],
            delta_rows,
        ),
    ]


def charts(summaries, differences):
    """Three static plots: overall, paired differences, and activity comparisons."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm

    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.facecolor": "white",
        }
    )
    figures = []
    overall = summaries[summaries["slice"] == "overall"]
    fig, ax = plt.subplots(figsize=(9, 4.5), layout="constrained")
    for i, row in enumerate(overall.itertuples()):
        ax.bar(i, row.mean, color=COLORS[i], width=0.6)
        ax.vlines(i, row.low, row.high, color="#222222", linewidth=2)
        ax.plot([i, i], [row.low, row.high], "_", color="#222222")
    ax.set(
        xticks=range(4),
        xticklabels=STRATEGIES,
        ylim=(0, 1),
        xlabel="Feed strategy",
        ylabel="Mean NDCG@10 (95% bootstrap interval)",
        title="Which strategy finds later likes in the top 10?",
    )
    figures.append(fig)

    fig, ax = plt.subplots(figsize=(10, 6), layout="constrained")
    present = differences[differences.users > 0]
    span = max(0.01, float(max(present.low.abs().max(), present.high.abs().max())) * 1.2)
    norm = TwoSlopeNorm(vmin=-span, vcenter=0, vmax=span)
    for i, row in enumerate(differences.itertuples()):
        if row.users:
            ax.hlines(i, row.low, row.high, color="#444444", linewidth=2)
            ax.scatter(
                row.mean,
                i,
                c=[plt.get_cmap("RdBu")(norm(row.mean))],
                edgecolors="#333333",
                s=75,
                zorder=3,
            )
        else:
            ax.text(0.01, i, "no eligible users", va="center", fontsize=9)
    labels = [f"{r.slice} (n={r.users})\nvs {r.baseline}" for r in differences.itertuples()]
    ax.axvline(0, color="#333333", linestyle="--", linewidth=1)
    ax.set(
        yticks=range(len(labels)),
        yticklabels=labels,
        xlim=(-span, span),
        xlabel="Mean NDCG@10 difference (95% paired interval)",
        ylabel="User slice",
        title="Where does learned win or lose against the best baseline?",
    )
    ax.invert_yaxis()
    fig.colorbar(
        plt.cm.ScalarMappable(norm=norm, cmap="RdBu"),
        ax=ax,
        label="Learned - baseline (negative = worse)",
        shrink=0.7,
    )
    figures.append(fig)

    fig, axes = plt.subplots(2, 2, figsize=(10, 7), sharex=True, sharey=True, layout="constrained")
    for ax, group in zip(axes.flat, GROUPS):
        part = summaries[summaries["slice"] == group]
        for j, row in enumerate(part.itertuples()):
            ax.hlines(j, row.low, row.high, color=COLORS[j], linewidth=2)
            ax.scatter(row.mean, j, color=COLORS[j], s=35, zorder=3)
        n = int(part.users.iloc[0]) if len(part) else 0
        ax.set(
            title=f"{group}, n={n}",
            xlim=(0, 1),
            ylim=(3.5, -0.5),
            yticks=range(4),
            yticklabels=STRATEGIES,
            xlabel="Mean NDCG@10 (95% interval)",
            ylabel="Feed strategy",
        )
        ax.tick_params(labelleft=True)
        if not n:
            ax.text(0.5, 1.5, "No eligible users", ha="center")
    fig.suptitle("Does user activity change the strategy comparison?")
    figures.append(fig)
    images = []
    for fig in figures:
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=140)
        images.append(base64.b64encode(buffer.getvalue()).decode("ascii"))
        plt.close(fig)
    return images


NOTES = (
    "Each slice uses its best observed baseline, held fixed during bootstrap. Intervals "
    "do not adjust for baseline selection or multiple comparisons. Empty groups are n/a; "
    "a one-user interval cannot describe population uncertainty. MovieLens results do not "
    "establish a winner for fresh social posts and are not comparable with the lab's "
    "one-like-among-100-candidates scores."
)


def write_reports(out, results, summaries, differences, metadata, overlap):
    out.mkdir(parents=True, exist_ok=True)
    results.to_csv(out / "eval_results.csv", index=False, float_format="%.12f", lineterminator="\n")
    tables = display_tables(summaries, differences)
    text = ["# Week 7 — Feed evaluation", "", "## Run metadata", ""]
    text += [f"- {key}: `{value}`" for key, value in metadata.items()]
    for title, (headings, rows) in zip(("Baselines", "Learned minus best baseline"), tables):
        text += [
            "",
            f"## {title}",
            "",
            "| " + " | ".join(headings) + " |",
            "| " + " | ".join(["---"] * len(headings)) + " |",
        ]
        text += ["| " + " | ".join(row) + " |" for row in rows]
    text += ["", "## Interpretation limits", "", overlap, "", NOTES, ""]
    (out / "baseline_table.md").write_text("\n".join(text), encoding="utf-8")

    def table_html(headings, rows):
        table = pd.DataFrame(rows, columns=headings).to_html(index=False, border=0)
        return f"<div class='table-wrap'>{table}</div>"

    meta = "".join(
        f"<dt>{html.escape(key)}</dt><dd>{html.escape(str(value))}</dd>"
        for key, value in metadata.items()
    )
    titles = [
        "Which strategy finds later likes in the top 10?",
        "Where does learned win or lose against the best baseline?",
        "Does user activity change the strategy comparison?",
    ]
    plots = "".join(
        f"<figure><img alt='{html.escape(title)}' src='data:image/png;base64,{encoded}'></figure>"
        for title, encoded in zip(titles, charts(summaries, differences))
    )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>InstaKill — Week 7 feed evaluation</title>
<style>
body {{font: 16px/1.6 system-ui, sans-serif; color: #26313d; background: #f4f3ef; margin: 0}}
main {{max-width: 1080px; margin: auto; padding: 32px 20px}}
h1,h2 {{line-height: 1.2}} h1 {{font-size: 2rem}} h2 {{margin-top: 36px; font-size: 1.3rem}}
table {{border-collapse: collapse; width: 100%; background: white; font-size: 14px}}
th,td {{padding: 12px; text-align: left; border-bottom: 1px solid #d4d8dc}}
th {{background: #e8ebee}} .table-wrap {{overflow-x: auto}}
figure {{margin: 24px 0; background: white; padding: 12px}} img {{width: 100%; height: auto}}
dl {{display: grid; grid-template-columns: minmax(180px, 1fr) 3fr; gap: 8px 16px}}
dd {{margin: 0; overflow-wrap: anywhere}} dt {{font-weight: 600}}
.note {{border-left: 4px solid #774594; padding: 12px 20px; background: white}}
@media (max-width: 640px) {{dl {{display: block}} dd {{margin-bottom: 12px}}}}
</style></head><body><main>
<p>Programming for AI · Week 7 · Elena Podariu-Ungureanu</p>
<h1>How well does the feed find later likes?</h1>
<p>Offline replay on a historical copy of InstaKill. Each eligible user receives one
top-10 feed per strategy. Higher NDCG@10 means more relevant posts near the top.</p>
<h2>Four strategies, the same users</h2>{table_html(*tables[0])}
<h2>Learned minus the best baseline</h2>{table_html(*tables[1])}
<p>Wins: the whole interval is above zero. Loses: below zero. Otherwise: unclear.
No eligible users means no estimate is available.</p>
{plots}
<h2>What these results can tell us</h2><p class="note">{html.escape(overlap)}</p>
<p>{html.escape(NOTES)}</p>
<h2>Run metadata</h2><dl>{meta}</dl>
</main></body></html>
"""
    (out / "dashboard.html").write_text(page, encoding="utf-8")


def evaluate(db: Path, out: Path, cutoff: datetime | None = None, seed: int = 42):
    if seed < 0:
        raise ValueError("Use a nonnegative random seed.")
    with TemporaryDirectory(prefix="instakill-eval-") as directory:
        snapshot = Path(directory) / "snapshot.db"
        cutoff, likes, posts, counts, movies, fingerprint = build_snapshot(db, snapshot, cutoff)
        results, fresh_users, _ = replay(snapshot, cutoff, likes, posts, counts)
    summaries, differences = summarize(results, seed)
    metadata = run_metadata(cutoff, likes, posts, results, fingerprint, seed)
    metadata["Users with relevant posts at most 7 days old at T"] = len(fresh_users)
    overlap = model_overlap(likes, results, posts, movies, cutoff)
    write_reports(out, results, summaries, differences, metadata, overlap)
    return results, summaries, differences


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=database_path())
    parser.add_argument(
        "--cutoff", type=parse_time, help="ISO date; default: 80th percentile of likes"
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=ROOT / "reports")
    args = parser.parse_args()
    try:
        results, _, _ = evaluate(args.db, args.out, args.cutoff, args.seed)
    except (ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"Evaluation failed: {exc}\n")
    print(f"Evaluated {results.user_id.nunique()} users; reports saved to {args.out}.")


if __name__ == "__main__":
    main()
