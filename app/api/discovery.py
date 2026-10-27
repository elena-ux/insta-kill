"""Thin HTTP adapters. Blocking I/O/model work runs in FastAPI's thread pool."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.application.search import SearchMode, SearchResponse, SearchService
from app.infrastructure.encoder import SearchUnavailable

router = APIRouter()
logger = logging.getLogger(__name__)


def search_service(request: Request) -> SearchService:
    return request.app.state.search_service



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
