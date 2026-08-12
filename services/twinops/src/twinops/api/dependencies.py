"""Small dependency helpers shared by API routes."""

from fastapi import Request

from twinops.storage.repository import TelemetryRepository


def repository_from_request(request: Request) -> TelemetryRepository:
    return request.app.state.repository
