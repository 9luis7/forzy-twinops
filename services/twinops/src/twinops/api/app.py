"""FastAPI composition root."""

from fastapi import FastAPI

from twinops.copilot.providers import build_configured_providers
from twinops.copilot.service import CopilotService

from .copilot_routes import create_copilot_router


def create_app(*, copilot_service: CopilotService | None = None) -> FastAPI:
    app = FastAPI(title="Forzy TwinOps API", version="0.1.0")
    service = copilot_service or CopilotService(build_configured_providers())
    app.include_router(create_copilot_router(service))
    return app


app = create_app()
