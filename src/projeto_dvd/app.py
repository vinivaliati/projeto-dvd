"""Web application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from projeto_dvd.api import health, library
from projeto_dvd.config import Settings
from projeto_dvd.db.session import make_engine, migrate


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. uvicorn calls it with --factory; tests pass their own settings."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        migrate(settings.database_url)
        yield
        app.state.engine.dispose()

    app = FastAPI(title="projeto-dvd", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    app.mount("/static", StaticFiles(directory=library.WEB_DIR / "static"), name="static")
    app.include_router(health.router)
    app.include_router(library.router)
    return app
