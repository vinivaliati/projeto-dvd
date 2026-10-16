"""Web application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from projeto_dvd.api import curation, dvd, health, jobs, library
from projeto_dvd.api.deps import WEB_DIR
from projeto_dvd.api.security import SameOriginMiddleware
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
    # Only localhost: a DNS-rebinding page (evil.example resolving to 127.0.0.1) is refused.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(SameOriginMiddleware)
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
    app.include_router(health.router)
    app.include_router(library.router)
    app.include_router(jobs.router)
    app.include_router(dvd.router)
    app.include_router(curation.router)
    return app
