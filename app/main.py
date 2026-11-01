from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.discovery import router
from app.application.feed import FeedService
from app.application.search import SearchService
from app.db.database import init_db
from app.db.repository import SQLitePostRepository
from app.infrastructure.encoder import SentenceEncoder


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="InstaKill", lifespan=lifespan)
    repository = SQLitePostRepository()
    app.state.search_service = SearchService(repository, SentenceEncoder())
    app.state.feed_service = FeedService(repository)
    app.include_router(router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    def home():
        return RedirectResponse("/search/")

    dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    # The API and /health start even before npm has built the interface.
    if dist.is_dir():
        app.mount("/search", StaticFiles(directory=dist, html=True), name="discovery-ui")
    return app


app = create_app()
