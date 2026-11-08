"""Build signals and the feed from data supplied by the repository."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, FiniteFloat

from app.infrastructure.like_model import LearnedUnavailable
from app.learned import Model, rank_learned
from app.ranking import FeedSignals, FeedWeights, chronological_feed, rank_feed, utc

FeedStrategy = Literal["for_you", "chronological", "learned"]


class UnknownUser(ValueError):
    pass


class FeedItem(BaseModel):
    post_id: int
    user_id: int
    content: str
    created_at: datetime
    score: FiniteFloat | None = None


class FeedResponse(BaseModel):
    user_id: int
    strategy: FeedStrategy
    posts: list[FeedItem]


def freshness(created_at: datetime, now: datetime) -> float:
    """Start at 1 and halve every 72 hours to favor newer posts."""
    age_hours = max(0.0, (utc(now) - utc(created_at)).total_seconds() / 3600)
    return 0.5 ** (age_hours / 72)


def affinity(author_id: int, followed_authors: set[int]) -> float:
    """Use following an author as an explicit preference: 1 or 0."""
    return 1.0 if author_id in followed_authors else 0.0


def popularity(likes: int, maximum_likes: int) -> float:
    """Normalize likes by the maximum; return 0 when there are no likes."""
    return likes / maximum_likes if maximum_likes else 0.0


class FeedService:
    def __init__(
        self, repository, weights: FeedWeights | None = None, like_model: Model | None = None
    ) -> None:
        self.repository = repository
        self.weights = weights if weights is not None else FeedWeights()
        self.like_model = like_model

    def build(
        self, user_id: int, now: datetime, strategy: FeedStrategy = "for_you", limit: int = 20
    ) -> FeedResponse:
        """Read candidates, apply the strategy, and build the feed response."""
        if (
            user_id <= 0
            or not 1 <= limit <= 50
            or strategy not in ("for_you", "chronological", "learned")
        ):
            raise ValueError("Invalid feed parameters.")
        now = utc(now)
        if strategy == "learned":
            snapshot = self.repository.learned_snapshot(user_id, now)
            if snapshot is None:
                raise UnknownUser("This user does not exist.")
            if self.like_model is None:
                raise LearnedUnavailable("Learned feed is unavailable. Try For you or Latest.")
            ranked = [
                (hit.post, hit.score)
                for hit in rank_learned(snapshot, user_id, now, self.like_model, limit)
            ]
        else:
            ranked = self._week4_feed(user_id, now, strategy, limit)
        return FeedResponse(
            user_id=user_id,
            strategy=strategy,
            posts=[
                FeedItem(
                    post_id=p.id,
                    user_id=p.user_id,
                    content=p.content,
                    created_at=p.created_at,
                    score=score,
                )
                for p, score in ranked
            ],
        )

    def _week4_feed(self, user_id: int, now: datetime, strategy: str, limit: int):
        """Keep the original formula and chronological strategy unchanged."""
        snapshot = self.repository.feed_snapshot(user_id, now)
        if snapshot is None:
            raise UnknownUser("This user does not exist.")
        candidates = snapshot.posts
        if strategy == "chronological":
            # The chronological strategy neither computes nor exposes a score.
            ranked = [(p, None) for p in chronological_feed(candidates, now, limit)]
        else:
            # Use the global maximum at now, not just the maximum among this user's candidates.
            max_likes = max(snapshot.like_counts.values(), default=0)
            signals = {}
            for post in candidates:
                # With no followed authors, affinity is 0 for every post.
                signals[post.id] = FeedSignals(
                    freshness=freshness(post.created_at, now),
                    affinity=affinity(post.user_id, snapshot.followed_authors),
                    popularity=popularity(snapshot.like_counts.get(post.id, 0), max_likes),
                )
            ranked = [
                (hit.post, hit.score)
                for hit in rank_feed(candidates, signals, now, self.weights, limit)
            ]
        return ranked
