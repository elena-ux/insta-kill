"""Thin HTTP adapters. Blocking I/O/model work runs in FastAPI's thread pool."""

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.application.feed import FeedResponse, FeedService, FeedStrategy, UnknownUser
from app.application.search import SearchMode, SearchResponse, SearchService
from app.infrastructure.encoder import SearchUnavailable

router = APIRouter()
logger = logging.getLogger(__name__)


def search_service(request: Request) -> SearchService:
    return request.app.state.search_service


def feed_service(request: Request) -> FeedService:
    """Provide the feed service created at application startup."""
    return request.app.state.feed_service


@router.get("/search", response_model=SearchResponse)
def search(
    q: Annotated[str, Query(min_length=1, max_length=500)],
    service: Annotated[SearchService, Depends(search_service)],
    limit: Annotated[int, Query(ge=1, le=50)] = 5,
    mode: SearchMode = "semantic",
) -> SearchResponse:
    if not q.strip():
        raise HTTPException(422, "Enter a query containing more than whitespace.")
    try:
        return service.search(q, mode, limit)
    except (SearchUnavailable, ValueError) as exc:
        logger.exception("Semantic search failed")
        raise HTTPException(
            503, "Search by meaning is unavailable. Try By words or retry later."
        ) from exc


@router.get("/feed", response_model=FeedResponse, response_model_exclude_none=True)
def feed(
    user_id: Annotated[int, Query(gt=0)],
    service: Annotated[FeedService, Depends(feed_service)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    strategy: FeedStrategy = "for_you",
) -> FeedResponse:
    """Accept parameters validated by FastAPI; return 404 for an unknown user."""
    try:
        # Read the clock at the API edge; pass the time to the ranker as an argument.
        return service.build(user_id, datetime.now(UTC), strategy, limit)
    except UnknownUser as exc:
        raise HTTPException(404, str(exc)) from exc
