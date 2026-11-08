"""Week 5 signals and predictions: NumPy calculations without database or clock access."""

import heapq
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from app.domain.models import Post
from app.ranking import RankedPost, utc

FEATURES = ["freshness", "affinity", "popularity", "activity", "lifetime", "age"]
Model = dict[str, np.ndarray]
DAY = 86_400


@dataclass(frozen=True)
class HistoricalLike:
    user_id: int
    post_id: int
    created_at: datetime


@dataclass
class LearnedSnapshot:
    posts: list[Post]
    categories: dict[int, set[str]]
    likes: list[HistoricalLike]


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -60, 60)))


def predict(saved: Model, features: np.ndarray) -> np.ndarray:
    """Notebook forward pass: raw signals (n, 6) -> estimated P(like)."""
    x = (features - saved["mu"]) / saved["sd"]
    hidden = np.tanh(x @ saved["W1"] + saved["b1"])
    return sigmoid((hidden @ saved["W2"] + saved["b2"])[:, 0])


def build_features(
    snapshot: LearnedSnapshot, user_id: int, now: datetime, saved: Model
) -> tuple[list[Post], np.ndarray]:
    """Build notebook signals, then exclude own and already-liked candidates."""
    now = utc(now)
    posts = [post for post in snapshot.posts if utc(post.created_at) < now]
    if not posts:
        return [], np.empty((0, len(FEATURES)))
    row_of = {post.id: row for row, post in enumerate(posts)}
    likes = [
        like for like in snapshot.likes if like.post_id in row_of and utc(like.created_at) < now
    ]

    # One column per category, just like the notebook's movie-genre matrix.
    names = sorted({name for post in posts for name in snapshot.categories.get(post.id, ())})
    column_of = {name: column for column, name in enumerate(names)}
    categories = np.zeros((len(posts), len(names)))
    for row, post in enumerate(posts):
        for name in snapshot.categories.get(post.id, ()):
            categories[row, column_of[name]] = 1.0

    # Count over the whole catalogue, not just this user's eligible candidates.
    like_rows = np.array([row_of[like.post_id] for like in likes], dtype=int)
    like_times = np.array([utc(like.created_at).timestamp() for like in likes])
    user_mask = np.array([like.user_id == user_id for like in likes], dtype=bool)
    recent_mask = like_times >= now.timestamp() - float(saved["popularity_days"]) * DAY
    lifetime_counts = np.bincount(like_rows, minlength=len(posts))
    recent_counts = np.bincount(like_rows[recent_mask], minlength=len(posts))
    user_counts = np.bincount(like_rows[user_mask], minlength=len(posts))

    # A liked post contributes once to each of its categories.
    category_counts = user_counts @ categories
    total = category_counts.sum()
    affinity = np.zeros(len(posts))
    if total > 0:
        affinity = (categories @ category_counts) / (total * np.maximum(categories.sum(axis=1), 1))

    age_days = np.array([(now - utc(post.created_at)).total_seconds() / DAY for post in posts])
    freshness = 0.5 ** (age_days / float(saved["half_life_days"]))
    popularity = recent_counts / max(recent_counts.max(), 1)
    activity = np.full(
        len(posts), min(1.0, np.log1p(user_counts.sum()) / np.log1p(saved["activity_cap"]))
    )
    lifetime = np.log1p(lifetime_counts) / np.log1p(max(lifetime_counts.max(), 1))
    age = np.minimum(1.0, age_days / float(saved["age_cap_days"]))
    features = np.column_stack([freshness, affinity, popularity, activity, lifetime, age])

    eligible = [
        row for row, post in enumerate(posts) if post.user_id != user_id and user_counts[row] == 0
    ]
    return [posts[row] for row in eligible], features[eligible]


def rank_learned(
    snapshot: LearnedSnapshot, user_id: int, now: datetime, saved: Model, limit: int
) -> list[RankedPost]:
    """Score candidates together and select top-k; lower IDs break score ties."""
    if limit < 0:
        raise ValueError("Use a nonnegative limit.")
    posts, features = build_features(snapshot, user_id, now, saved)
    scored = (
        RankedPost(post, float(score)) for post, score in zip(posts, predict(saved, features))
    )
    return heapq.nsmallest(limit, scored, key=lambda hit: (-hit.score, hit.post.id))
