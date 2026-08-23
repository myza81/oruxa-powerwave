"""Powerwave API application.

Served via uvicorn's factory mode (``app.main:create_app --factory``) so that
importing this module has no side effects at all: no environment reads, no
filesystem access, and nothing to stub out in tests.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from app.api.v1.calculated_channels import router as calculated_channels_v1_router
from app.api.v1.per_unit import router as per_unit_v1_router
from app.api.v1.sources import router as sources_v1_router
from app.api.v1.workspaces import router as workspaces_v1_router
from app.config import Settings, load_settings
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.per_unit_registry import PerUnitRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.workspace_registry import WorkspaceRegistry
from app.storage import StorageBackend, get_storage

# Multipart body overhead (boundaries, part headers) beyond the raw file
# bytes -- generous margin so a legitimate upload right at the configured
# limit is never rejected by this fast pre-check.
_MULTIPART_OVERHEAD_BYTES = 1024 * 1024


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
        # In-memory only, per docs/project-memory/MIGRATION_PLAN.md's
        # Critical New Storage Decision: source metadata lives here for the
        # life of the process; nothing about an uploaded event file is ever
        # written to StorageBackend. See app/services/workspace_registry.py.
        app.state.workspace_registry = WorkspaceRegistry()
        # Phase 5A (DEC-047): a separate, sibling in-memory registry for
        # calculated channels -- see app.services.calculated_channel_registry's
        # own module docstring for why this is not folded into
        # WorkspaceRegistry itself.
        app.state.calculated_channel_registry = CalculatedChannelRegistry()
        # Phase 5C (DEC-049): a third sibling in-memory registry, same
        # structural shape as the two above -- see
        # app.services.per_unit_registry's own module docstring.
        app.state.per_unit_registry = PerUnitRegistry()
        # Slice 1 (DEC-050): a fourth sibling in-memory registry -- internal
        # scaffolding for the future measurement-group-aware Per-Unit
        # redesign, not yet wired into any API router. See
        # app.services.measurement_group_registry's own module docstring.
        app.state.measurement_group_registry = MeasurementGroupRegistry()
        # Slice 3 (DEC-050): a fifth sibling in-memory registry -- Voltage
        # measurement-group base configuration, not yet wired into any API
        # router. See app.services.voltage_group_config_registry's own
        # module docstring.
        app.state.voltage_group_config_registry = VoltageGroupConfigRegistry()
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

    @app.middleware("http")
    async def reject_oversized_uploads(request: Request, call_next):
        """Fast-path rejection using Content-Length, before any multipart parsing.

        This is a pre-check, not the authoritative enforcement -- Content-Length
        can be absent or (in principle) inaccurate. The authoritative check is
        in app.services.import_service, based on bytes actually read. See
        docs/project-memory/MIGRATION_PLAN.md's Phase 1 update and this
        phase's final report for the full investigation of what Starlette
        itself does with multipart uploads before either check runs.
        """
        if request.url.path.startswith("/api/v1/workspaces/") and request.method == "POST":
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    declared_size = int(content_length)
                except ValueError:
                    declared_size = None
                if declared_size is not None:
                    limit = settings.max_event_upload_size_bytes + _MULTIPART_OVERHEAD_BYTES
                    if declared_size > limit:
                        # Same {"detail": {"code", "message"}} shape FastAPI's
                        # HTTPException produces (app/api/v1/sources.py), so
                        # the frontend has exactly one error shape to parse
                        # regardless of which layer rejected the request.
                        return JSONResponse(
                            status_code=413,
                            content={
                                "detail": {
                                    "code": "upload_too_large",
                                    "message": (
                                        "Declared upload size exceeds the "
                                        f"{settings.max_event_upload_size_mb} MB limit."
                                    ),
                                }
                            },
                        )
        return await call_next(request)

    app.include_router(sources_v1_router)
    app.include_router(workspaces_v1_router)
    app.include_router(calculated_channels_v1_router)
    app.include_router(per_unit_v1_router)

    @app.get("/health")
    def health():
        # Phase 4A-UAT3: build provenance -- both fields come straight from
        # Settings (itself sourced only from the APP_VERSION environment
        # variable, see app.config.load_settings), never computed here by
        # inspecting the filesystem or running `git`.
        return {
            "status": "ok",
            "environment": settings.environment,
            "version": settings.version,
            "git_sha": settings.git_sha,
        }

    return app


def get_storage_backend(request: Request) -> StorageBackend:
    """FastAPI dependency exposing the storage backend to route handlers."""
    return request.app.state.storage


# Note: app.api.v1.sources and app.api.v1.workspaces each define their own
# get_workspace_registry(request) dependency (same request.app.state.
# workspace_registry pattern as above) rather than importing it from here,
# to avoid a circular import (this module imports both routers).
