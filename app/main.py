from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.discovery import router
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
    app.include_router(router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
