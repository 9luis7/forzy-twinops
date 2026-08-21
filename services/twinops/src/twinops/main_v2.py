"""Injectable and environment-backed composition roots for TwinOps v2."""

from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
import os

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from twinops.api.v2_routes import PUBLIC_ASSET_ID, create_v2_router
from twinops.config_v2 import SettingsV2
from twinops.ingestion.refresh_service import RefreshService
from twinops.ingestion.schedule import CollectionWindow
from twinops.ingestion.upstream import UpstreamClient
from twinops.ml.runtime import load_assessment_scorer
from twinops.ml.scorer import AssessmentScorer
from twinops.storage.postgres_repository import PostgresTelemetryRepository
from twinops.storage.sqlite_v2_repository import SQLiteTelemetryRepositoryV2
from twinops.storage.v2_repository import TelemetryRepositoryV2


class _UnavailableAssessmentScorer:
    def assess(self, samples, *, now):
        return None


class _UnavailableRefreshService:
    async def refresh(self, now):
        raise RuntimeError("application_not_started")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_app_v2(
    *,
    repository: TelemetryRepositoryV2,
    settings: SettingsV2,
    refresh_service: RefreshService,
    assessment_scorer: AssessmentScorer | None,
    clock: Callable[[], datetime],
) -> FastAPI:
    app = FastAPI(title="Forzy TwinOps API", version="2.0.0")
    app.state.repository = repository
    app.state.settings = settings
    app.state.refresh_service = refresh_service
    app.state.assessment_scorer = assessment_scorer or _UnavailableAssessmentScorer()
    app.state.clock = clock
    app.include_router(create_v2_router())

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logging.getLogger("twinops.api").error(
            "request_failed error_type=%s path=%s",
            type(exc).__name__,
            request.url.path,
        )
        return JSONResponse(status_code=500, content={"detail": "internal_error"})

    return app


def create_app_v2_from_env(
    env: Mapping[str, str] | None = None,
    *,
    clock: Callable[[], datetime] = utc_now,
) -> FastAPI:
    """Build the deployable app without opening files, sockets, or models."""

    source_env = os.environ if env is None else env
    settings = SettingsV2.from_env(source_env)
    if source_env.get("VERCEL") == "1":
        settings = settings.for_deploy()
    repository: TelemetryRepositoryV2
    if settings.database_url is not None:
        repository = PostgresTelemetryRepository(settings.database_url)
    else:
        repository = SQLiteTelemetryRepositoryV2(settings.database_path)

    app = create_app_v2(
        repository=repository,
        settings=settings,
        refresh_service=_UnavailableRefreshService(),
        assessment_scorer=None,
        clock=clock,
    )
    app.router.lifespan_context = _runtime_lifespan(settings, repository)
    return app


def _runtime_lifespan(settings: SettingsV2, repository: TelemetryRepositoryV2):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repository.initialize()
        scorer = _load_configured_scorer(settings)
        async with httpx.AsyncClient() as http:
            app.state.refresh_service = RefreshService(
                UpstreamClient(
                    http,
                    settings.upstream_base_url,
                    settings.request_timeout_seconds,
                ),
                repository,
                asset_id=PUBLIC_ASSET_ID,
                window=CollectionWindow(settings.timezone_name),
                poll_interval_seconds=settings.poll_interval_seconds,
                clock=app.state.clock,
            )
            app.state.assessment_scorer = scorer or _UnavailableAssessmentScorer()
            try:
                yield
            finally:
                app.state.refresh_service = _UnavailableRefreshService()
                app.state.assessment_scorer = _UnavailableAssessmentScorer()

    return lifespan


def _load_configured_scorer(settings: SettingsV2) -> AssessmentScorer | None:
    anchors = (
        settings.ml_artifact_path,
        settings.ml_manifest_hash,
        settings.ml_model_hash,
    )
    if not all(anchor is not None for anchor in anchors):
        return None
    assert settings.ml_artifact_path is not None
    assert settings.ml_manifest_hash is not None
    assert settings.ml_model_hash is not None
    try:
        return load_assessment_scorer(
            settings.ml_artifact_path,
            expected_manifest_hash=settings.ml_manifest_hash,
            expected_model_hash=settings.ml_model_hash,
        )
    except Exception as exc:
        logging.getLogger("twinops.api").error(
            "assessment_scorer_startup_failed error_type=%s",
            type(exc).__name__,
        )
        raise RuntimeError("assessment_scorer_startup_failed") from None
