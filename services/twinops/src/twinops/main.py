"""FastAPI composition root for TwinOps."""

from collections.abc import Callable
from datetime import datetime, timezone
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from twinops.api.health_routes import router as health_router
from twinops.api.telemetry_routes import router as telemetry_router
from twinops.config import Settings
from twinops.storage.repository import TelemetryRepository


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_app(
    repository: TelemetryRepository,
    settings: Settings,
    collector=None,
    clock: Callable[[], datetime] = utc_now,
) -> FastAPI:
    app = FastAPI(title="Forzy TwinOps API", version="1.0.0")
    app.state.repository = repository
    app.state.settings = settings
    app.state.collector = collector
    app.state.clock = clock
    app.include_router(telemetry_router)
    app.include_router(health_router)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logging.getLogger("twinops.api").error(
            "request_failed error_type=%s path=%s",
            type(exc).__name__,
            request.url.path,
        )
        return JSONResponse(status_code=500, content={"detail": "internal_error"})

    return app
