"""Thin HTTP adapters. Blocking I/O/model work runs in FastAPI's thread pool."""

import logging
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.application.feed import FeedResponse, FeedService, FeedStrategy, UnknownUser
from app.application.post_drafts import prepare_post_draft
from app.application.search import SearchMode, SearchResponse, SearchService
from app.domain.models import Post
from app.infrastructure.encoder import SearchUnavailable
from app.infrastructure.like_model import LearnedUnavailable

router = APIRouter()
logger = logging.getLogger(__name__)
Collection = Literal["community", "movies"]


def search_service(request: Request) -> SearchService:
    return request.app.state.search_service


def feed_service(request: Request) -> FeedService:
    """Provide the feed service created at application startup."""
    return request.app.state.feed_service


@router.get("/dataset")
def dataset(
    request: Request,
    service: Annotated[FeedService, Depends(feed_service)],
    collection: Collection | None = None,
) -> dict:
    info = service.repository.dataset_info(collection)
    if collection is None:
        info["default_collection"] = request.app.state.default_collection
        info["collections"] = {
            name: service.repository.dataset_info(name) for name in ("community", "movies")
        }
    return info


class DraftRequest(BaseModel):
    user_id: int = Field(gt=0)
    content: str = Field(min_length=1, max_length=5000)


@router.post("/posts/preview", response_model=Post)
def preview(body: DraftRequest, service: Annotated[FeedService, Depends(feed_service)]) -> Post:
    author = service.repository.user(body.user_id)
    if author is None:
        raise HTTPException(404, "This user does not exist.")
    try:
        return prepare_post_draft(author=author, content=body.content)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/search", response_model=SearchResponse)
def search(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    service: Annotated[SearchService, Depends(search_service)],
    limit: Annotated[int, Query(ge=1, le=50)] = 5,
    mode: SearchMode = "semantic",
    collection: Collection | None = None,
) -> SearchResponse:
    if not q.strip():
        raise HTTPException(422, "Enter a query containing more than whitespace.")
    try:
        return service.search(q, mode, limit, collection or request.app.state.default_collection)
    except (SearchUnavailable, ValueError) as exc:
        logger.exception("Semantic search failed")
        raise HTTPException(
            503, "Search by meaning is unavailable. Try By words or retry later."
        ) from exc


@router.get("/feed", response_model=FeedResponse, response_model_exclude_none=True)
def feed(
    request: Request,
    user_id: Annotated[int, Query(gt=0)],
    service: Annotated[FeedService, Depends(feed_service)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    strategy: FeedStrategy = "for_you",
    collection: Collection | None = None,
) -> FeedResponse:
    """Accept parameters validated by FastAPI; return 404 for an unknown user."""
    try:
        # MovieLens replays its historical snapshot; ordinary feeds use request time.
        collection = collection or request.app.state.default_collection
        demo_time = request.app.state.demo_time if collection == "movies" else None
        now = datetime.fromisoformat(demo_time) if demo_time else datetime.now(UTC)
        return service.build(user_id, now, strategy, limit, collection)
    except UnknownUser as exc:
        raise HTTPException(404, str(exc)) from exc
    except LearnedUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
