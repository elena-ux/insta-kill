import logging
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
from app.infrastructure.like_model import MODEL_PATH, LearnedUnavailable, load_model

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    info = app.state.feed_service.repository.dataset_info()
    app.state.demo_time = info["reference_time"]
    app.state.default_collection = "movies" if info["source"] == "movielens" else "community"
    yield


def create_app(*, like_model_path: Path = MODEL_PATH) -> FastAPI:
    app = FastAPI(title="InstaKill", lifespan=lifespan)
    app.state.demo_time = None
    app.state.default_collection = "community"
    repository = SQLitePostRepository()
    app.state.search_service = SearchService(repository, SentenceEncoder())
    try:
        like_model = load_model(like_model_path)
    except LearnedUnavailable:
        logger.warning("Week 5 model unavailable; other feed strategies remain available.")
        like_model = None
    app.state.feed_service = FeedService(repository, like_model=like_model)
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
