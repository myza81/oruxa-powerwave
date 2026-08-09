"""Powerwave API application.

Served via uvicorn's factory mode (``app.main:create_app --factory``) so that
importing this module has no side effects at all: no environment reads, no
filesystem access, and nothing to stub out in tests.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, load_settings
from app.storage import StorageBackend, get_storage


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    Settings are resolved here rather than at module scope so tests can supply
    their own, and storage is constructed during startup rather than at import
    time so importing this module never touches the filesystem.
    """
    settings = load_settings() if settings is None else settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.storage = get_storage(settings)
        yield

    app = FastAPI(title="Powerwave API", lifespan=lifespan)
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {"status": "ok", "environment": settings.environment}

    return app


def get_storage_backend(request: Request) -> StorageBackend:
    """FastAPI dependency exposing the storage backend to route handlers."""
    return request.app.state.storage
