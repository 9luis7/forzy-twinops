"""Bounded demo HTTP requests; authentication and revisions belong to repository."""

import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, ValidationError
from starlette.responses import JSONResponse

from twinops.rag.public_models import AssistantQueryRequest
from twinops.rag.request_limits import MAX_ASSISTANT_REQUEST_BYTES
from twinops.rag.retrieval import CorpusUnavailableError


class DemoQueryRequest(AssistantQueryRequest):
    context_revision: int | None = Field(default=None, alias="contextRevision", ge=0, strict=True)


def _error(status, detail):
    return HTTPException(status_code=status, detail=detail, headers={"Cache-Control": "no-store"})


async def _body(request, max_bytes):
    # Bound the streamed body before JSON/Pydantic parsing, including chunked
    # requests. This works without changing the existing live middleware.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes:
        raise _error(413, "assistant_request_too_large")
    parts, count = [], 0
    async for part in request.stream():
        count += len(part)
        if count > max_bytes:
            raise _error(413, "assistant_request_too_large")
        parts.append(part)
    try:
        result = json.loads(b"".join(parts))
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise _error(422, "invalid_request") from None
    if not isinstance(result, dict):
        raise _error(422, "invalid_request")
    return result


def _service_and_token(request):
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or token != token.strip():
        raise _error(404, "run_not_found")
    service = getattr(request.app.state, "demo_assistant_service", None)
    if service is None:
        raise _error(503, "demo_assistant_unavailable")
    return service, token


async def _invoke(call):
    try:
        result = await call
    except (CorpusUnavailableError, TimeoutError):
        raise _error(503, "demo_assistant_unavailable") from None
    except Exception as error:
        from twinops.demo.repository import DemoError
        if isinstance(error, DemoError):
            raise _error(error.status_code, error.detail) from None
        raise _error(503, "demo_assistant_unavailable") from None
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


def create_demo_rag_router():
    router = APIRouter(prefix="/api/demo/v1/runs", tags=["demo-assistant"])

    @router.post("/{run_id}/assistant/query")
    async def query(run_id: str, request: Request):
        service, token = _service_and_token(request)
        raw = await _body(request, MAX_ASSISTANT_REQUEST_BYTES)
        try:
            body = DemoQueryRequest.model_validate(raw)
        except ValidationError:
            raise _error(422, "invalid_request") from None
        assistant_request = AssistantQueryRequest(
            question=body.question, conversationId=body.conversation_id,
            history=body.history,
        )
        return await _invoke(service.query(run_id, token, assistant_request, body.context_revision))

    @router.post("/{run_id}/events/{event_id}/recommendation")
    async def recommendation(run_id: str, event_id: str, request: Request):
        service, token = _service_and_token(request)
        if await _body(request, 4096):
            raise _error(422, "invalid_request")
        return await _invoke(service.recommendation(run_id, token, event_id))

    return router
