"""Rank the feed without clock, database, or HTTP access."""

import heapq
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.domain.models import Post


@dataclass(frozen=True)
class FeedSignals:
    """Three signals for a post, each between 0 and 1."""

    freshness: float
    affinity: float
    popularity: float


@dataclass(frozen=True)
class FeedWeights:
    # Prioritize followed authors with +2 points; these weights are not yet evaluated.
    # The other two signals together add at most 2 points.
    freshness: float = 1.0
    affinity: float = 2.0
    popularity: float = 1.0


@dataclass(frozen=True)
class RankedPost:
    post: Post
    score: float


def utc(value: datetime) -> datetime:
    """Treat SQLite timestamps without a timezone as UTC for consistent comparisons."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def rank_feed(
    candidates: Sequence[Post],
    signals: Mapping[int, FeedSignals],
    now: datetime,
    weights: FeedWeights,
    limit: int,
) -> list[RankedPost]:
    """Select by score descending, then ID ascending, without changing the inputs."""
    if limit < 0:
        raise ValueError("Use a nonnegative limit.")
    for weight in (weights.freshness, weights.affinity, weights.popularity):
        if not math.isfinite(weight) or weight < 0:
            raise ValueError("Use nonnegative finite weights.")

    scored = []
    for post in candidates:
        if post.id is None or post.created_at is None:
            raise ValueError("Feed posts require an ID and created_at.")
        if utc(post.created_at) > utc(now):
            continue
        values = signals[post.id]
        if any(
            not math.isfinite(v) or not 0 <= v <= 1
            for v in (values.freshness, values.affinity, values.popularity)
        ):
            raise ValueError("Signals must be finite numbers between zero and one.")
        score = (
            weights.freshness * values.freshness
            + weights.affinity * values.affinity
            + weights.popularity * values.popularity
        )
        scored.append(RankedPost(post, score))
    # Negating the score puts higher scores first; ID breaks ties.
    # The heap selects top-k without sorting all scores when k is small.
    return heapq.nsmallest(limit, scored, key=lambda hit: (-hit.score, hit.post.id))


def chronological_feed(candidates: Sequence[Post], now: datetime, limit: int) -> list[Post]:
    """Return the newest eligible posts, breaking ties by the lower ID."""
    eligible = (p for p in candidates if p.created_at is not None and utc(p.created_at) <= utc(now))
    return heapq.nsmallest(limit, eligible, key=lambda p: (-utc(p.created_at).timestamp(), p.id))
