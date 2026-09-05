"""Injectable and environment-backed composition roots for TwinOps v2."""

from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import asyncio
import logging
import os
from time import monotonic

import httpx
import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from twinops.api.v2_routes import PUBLIC_ASSET_ID, create_v2_router
from twinops.config_v2 import SettingsV2
from twinops.demo.repository import DemoRepository
from twinops.demo.routes import create_demo_router
from twinops.demo.service import DemoService
from twinops.ingestion.refresh_service import RefreshService
from twinops.ingestion.schedule import CollectionWindow
from twinops.ingestion.upstream import UpstreamClient
from twinops.ml.runtime import load_assessment_scorer
from twinops.ml.scorer import AssessmentScorer
from twinops.rag.admin_routes import create_rag_admin_router
from twinops.rag.admin_service import RagAdminService
from twinops.rag.pdf import OfficialPdfSourceFetcher
from twinops.rag.embeddings import (
    EmbeddingClient,
    EmbeddingGatewayClient,
    GeminiEmbeddingClient,
)
from twinops.rag.generation import ChatGatewayClient, GeminiChatClient
from twinops.rag.demo_routes import create_demo_rag_router
from twinops.rag.demo_service import DemoAssistantService, DemoRagAssistantService
from twinops.rag.public_service import RagAssistantService
from twinops.rag.repository import PostgresRagRepository, RagRepository
from twinops.rag.request_limits import (
    RagAdminUploadLimitMiddleware,
    RagPublicQueryLimitMiddleware,
)
from twinops.rag.retrieval import HybridRetriever
from twinops.storage.postgres_repository import PostgresTelemetryRepository
from twinops.storage.sqlite_v2_repository import SQLiteTelemetryRepositoryV2
from twinops.storage.v2_repository import TelemetryRepositoryV2


class _UnavailableAssessmentScorer:
    def assess(self, samples, *, now):
        return None


class _UnavailableRefreshService:
    async def refresh(self, now):
        raise RuntimeError("application_not_started")


class _LiveAvailability:
    """Lazy live initialization isolates a dedicated demo and permits recovery."""

    retry_seconds = 30

    def __init__(self, repository: TelemetryRepositoryV2):
        self.repository = repository
        self.ready = False
        self.retry_at = 0.0
        self.lock = asyncio.Lock()

    def failed(self, error: Exception) -> None:
        self.ready = False
        self.retry_at = monotonic() + self.retry_seconds
        logging.getLogger("twinops.api").warning(
            "live_database_unavailable error_type=%s", type(error).__name__
        )

    async def ensure_ready(self) -> bool:
        if self.ready:
            return True
        if monotonic() < self.retry_at:
            return False
        async with self.lock:
            if self.ready:
                return True
            if monotonic() < self.retry_at:
                return False
            try:
                await asyncio.to_thread(self.repository.initialize)
            except Exception as error:
                self.failed(error)
                return False
            self.ready = True
            return True


def _is_live_database_route(path: str) -> bool:
    asset_prefix = f'/api/v2/assets/{PUBLIC_ASSET_ID}/'
    return (
        path == '/api/v2/integration/health'
        or path.startswith('/api/v2/admin/rag/')
        or (path.startswith(asset_prefix) and path[len(asset_prefix):] in {
            'snapshot', 'twin-context', 'history', 'refresh', 'assistant/query',
        })
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _build_embedding_clients(
    http,
    settings: SettingsV2,
) -> tuple[EmbeddingClient | None, EmbeddingClient | None]:
    api_key = settings.rag_api_key
    if api_key is None:
        return None, None
    common = {
        "api_key": api_key,
        "model": settings.rag_embedding_model,
        "dimensions": settings.rag_embedding_dimensions,
        "timeout_seconds": settings.rag_gateway_timeout_seconds,
    }
    if settings.rag_provider == "gemini":
        return (
            GeminiEmbeddingClient(
                http,
                task_type="RETRIEVAL_DOCUMENT",
                **common,
            ),
            GeminiEmbeddingClient(
                http,
                task_type="RETRIEVAL_QUERY",
                **common,
            ),
        )
    gateway_client = EmbeddingGatewayClient(http, **common)
    return gateway_client, gateway_client


def _build_chat_client(http, settings: SettingsV2, *, timeout_seconds=None):
    common = {
        "api_key": settings.rag_api_key or "",
        "model": settings.rag_generation_model,
        "timeout_seconds": (
            settings.rag_gateway_timeout_seconds
            if timeout_seconds is None else timeout_seconds
        ),
        "base_url": settings.rag_chat_base_url,
    }
    if settings.rag_provider == "gemini":
        return GeminiChatClient(http, **common)
    return ChatGatewayClient(http, **common)


def create_app_v2(
    *,
    repository: TelemetryRepositoryV2,
    settings: SettingsV2,
    refresh_service: RefreshService,
    assessment_scorer: AssessmentScorer | None,
    clock: Callable[[], datetime],
    rag_admin_service: RagAdminService | None = None,
    rag_assistant_service: RagAssistantService | None = None,
    demo_service: DemoService | None = None,
    demo_assistant_service: DemoAssistantService | None = None,
) -> FastAPI:
    app = FastAPI(title="Forzy TwinOps API", version="2.0.0")
    app.state.repository = repository
    app.state.settings = settings
    app.state.refresh_service = refresh_service
    app.state.assessment_scorer = assessment_scorer or _UnavailableAssessmentScorer()
    app.state.clock = clock
    app.state.rag_admin_service = rag_admin_service
    app.state.rag_document_fetcher = None
    app.state.rag_assistant_service = rag_assistant_service
    app.state.demo_service = demo_service
    app.state.demo_assistant_service = demo_assistant_service
    app.state.live_availability = None
    app.include_router(create_v2_router())
    if settings.demo_enabled:
        app.include_router(create_demo_router())
        app.include_router(create_demo_rag_router())
    app.add_middleware(RagPublicQueryLimitMiddleware)
    if settings.vercel_environment == "preview" and settings.rag_admin_enabled:
        app.add_middleware(RagAdminUploadLimitMiddleware)
        app.include_router(create_rag_admin_router())

    @app.middleware('http')
    async def isolate_live_database(request: Request, call_next):
        availability = app.state.live_availability
        if availability is None or not _is_live_database_route(request.url.path):
            return await call_next(request)
        if await availability.ensure_ready():
            try:
                return await call_next(request)
            except psycopg.Error as error:
                availability.failed(error)
        return JSONResponse(
            status_code=503, content={"detail": "live_unavailable"},
            headers={"Cache-Control": "no-store", "Retry-After": str(availability.retry_seconds)},
        )

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
    rag_repository: RagRepository | None = None
    demo_rag_repository: RagRepository | None = None
    if settings.database_url is not None:
        connect_timeout_seconds = max(
            1, int(settings.rag_query_timeout_seconds)
        )
        statement_timeout_ms = max(
            1, int(settings.rag_query_timeout_seconds * 1_000)
        )
        repository = PostgresTelemetryRepository(
            settings.database_url,
            connect_timeout_seconds=connect_timeout_seconds,
            statement_timeout_ms=statement_timeout_ms,
        )
        rag_repository = PostgresRagRepository(
            settings.database_url,
            connect_timeout_seconds=connect_timeout_seconds,
            statement_timeout_ms=statement_timeout_ms,
        )
    else:
        repository = SQLiteTelemetryRepositoryV2(settings.database_path)
    if settings.has_dedicated_demo_database:
        demo_rag_repository = PostgresRagRepository(
            settings.demo_database_url,
            connect_timeout_seconds=max(1, int(settings.rag_query_timeout_seconds)),
            statement_timeout_ms=max(1, int(settings.rag_query_timeout_seconds * 1_000)),
        )

    app = create_app_v2(
        repository=repository,
        settings=settings,
        refresh_service=_UnavailableRefreshService(),
        assessment_scorer=None,
        clock=clock,
    )
    app.router.lifespan_context = _runtime_lifespan(
        settings, repository, rag_repository, demo_rag_repository
    )
    return app


def _runtime_lifespan(
    settings: SettingsV2,
    repository: TelemetryRepositoryV2,
    rag_repository: RagRepository | None,
    demo_rag_repository: RagRepository | None = None,
):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.has_dedicated_demo_database:
            app.state.live_availability = _LiveAvailability(repository)
        else:
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
            demo_repository = None
            if settings.demo_enabled:
                demo_repository = DemoRepository(
                    settings.effective_demo_database_url or (
                        "sqlite:///" + str(settings.database_path.with_name("demo.sqlite3"))
                    ),
                    clock=app.state.clock,
                )
                app.state.demo_service = DemoService(
                    demo_repository, app.state.assessment_scorer, app.state.clock,
                )
            document_embedding_client = None
            query_embedding_client = None
            demo_corpus_repository = (
                demo_rag_repository if settings.has_dedicated_demo_database else rag_repository
            )
            if rag_repository is not None or demo_corpus_repository is not None:
                document_embedding_client, query_embedding_client = (
                    _build_embedding_clients(http, settings)
                )
            if (
                settings.rag_enabled
                and rag_repository is not None
                and query_embedding_client is not None
            ):
                assert settings.rag_manufacturer is not None
                assert settings.rag_equipment_model is not None
                app.state.rag_assistant_service = RagAssistantService(
                    HybridRetriever(
                        rag_repository,
                        query_embedding_client,
                        manufacturer=settings.rag_manufacturer,
                        equipment_model=settings.rag_equipment_model,
                    ),
                    _build_chat_client(http, settings),
                    query_timeout_seconds=settings.rag_query_timeout_seconds,
                )
            if (
                settings.rag_enabled and demo_repository is not None
                and demo_corpus_repository is not None and query_embedding_client is not None
            ):
                app.state.demo_assistant_service = DemoAssistantService(
                    demo_repository,
                    DemoRagAssistantService(
                        HybridRetriever(
                            demo_corpus_repository, query_embedding_client,
                            manufacturer=settings.rag_manufacturer,
                            equipment_model=settings.rag_equipment_model,
                        ),
                        _build_chat_client(http, settings, timeout_seconds=30.0),
                    ),
                )
            if (
                rag_repository is not None
                and settings.vercel_environment == "preview"
                and settings.rag_admin_enabled
                and document_embedding_client is not None
                and query_embedding_client is not None
            ):
                assert settings.rag_manufacturer is not None
                assert settings.rag_equipment_model is not None
                app.state.rag_admin_service = RagAdminService(
                    rag_repository,
                    document_embedding_client,
                    query_embeddings=query_embedding_client,
                    manufacturer=settings.rag_manufacturer,
                    equipment_model=settings.rag_equipment_model,
                    acceptance_chat=_build_chat_client(http, settings),
                    query_timeout_seconds=settings.rag_query_timeout_seconds,
                )
                app.state.rag_document_fetcher = OfficialPdfSourceFetcher(
                    http,
                    timeout_seconds=settings.rag_gateway_timeout_seconds,
                ).fetch
            try:
                yield
            finally:
                app.state.rag_document_fetcher = None
                app.state.refresh_service = _UnavailableRefreshService()
                app.state.assessment_scorer = _UnavailableAssessmentScorer()
                app.state.rag_admin_service = None
                app.state.rag_assistant_service = None
                app.state.demo_service = None
                app.state.demo_assistant_service = None
                app.state.live_availability = None

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
