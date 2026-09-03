import pytest

from twinops.rag import request_limits
from twinops.rag.request_limits import RagAdminUploadLimitMiddleware


@pytest.mark.asyncio
async def test_upload_limit_counts_streamed_body_without_content_length_before_app_runs():
    reached_handler = False

    async def downstream(scope, receive, send):
        nonlocal reached_handler
        while True:
            message = await receive()
            if not message.get("more_body", False):
                break
        reached_handler = True

    messages = iter(
        [
            {"type": "http.request", "body": b"123", "more_body": True},
            {"type": "http.request", "body": b"456", "more_body": False},
        ]
    )
    sent = []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    middleware = RagAdminUploadLimitMiddleware(downstream, max_bytes=5)
    await middleware(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v2/admin/rag/corpora/c1/documents",
            "headers": [],
        },
        receive,
        send,
    )

    assert reached_handler is False
    assert sent[0]["status"] == 413
    assert b"upload_request_too_large" in sent[1]["body"]


@pytest.mark.asyncio
async def test_declared_oversized_upload_is_rejected_without_reading_body():
    called = False

    async def downstream(scope, receive, send):
        raise AssertionError("downstream must not run")

    async def receive():
        nonlocal called
        called = True
        raise AssertionError("body must not be read")

    sent = []

    async def send(message):
        sent.append(message)

    middleware = RagAdminUploadLimitMiddleware(downstream, max_bytes=5)
    await middleware(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v2/admin/rag/corpora/c1/documents",
            "headers": [(b"content-length", b"6")],
        },
        receive,
        send,
    )

    assert called is False
    assert sent[0]["status"] == 413


@pytest.mark.asyncio
async def test_stream_limit_cannot_be_masked_by_downstream_exception_handling():
    async def downstream(scope, receive, send):
        try:
            while True:
                message = await receive()
                if not message.get("more_body", False):
                    break
        except Exception:
            await send({"type": "http.response.start", "status": 500, "headers": []})
            await send({"type": "http.response.body", "body": b"internal_error"})

    messages = iter(
        [
            {"type": "http.request", "body": b"123", "more_body": True},
            {"type": "http.request", "body": b"456", "more_body": False},
        ]
    )
    sent = []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    middleware = RagAdminUploadLimitMiddleware(downstream, max_bytes=5)
    await middleware(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v2/admin/rag/corpora/c1/documents",
            "headers": [],
        },
        receive,
        send,
    )

    assert sent[0]["status"] == 413


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [[], [(b"content-length", b"6")]],
)
async def test_public_query_limit_rejects_streamed_and_declared_oversize_without_echo(
    headers,
):
    reached_handler = False
    body_reads = 0

    async def downstream(scope, receive, send):
        nonlocal reached_handler
        reached_handler = True

    messages = iter(
        [
            {"type": "http.request", "body": b"sec", "more_body": True},
            {"type": "http.request", "body": b"ret!", "more_body": False},
        ]
    )

    async def receive():
        nonlocal body_reads
        body_reads += 1
        return next(messages)

    sent = []

    async def send(message):
        sent.append(message)

    middleware = request_limits.RagPublicQueryLimitMiddleware(
        downstream, max_bytes=5
    )
    await middleware(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v2/assets/forzy-motor-01/assistant/query",
            "headers": headers,
        },
        receive,
        send,
    )

    assert reached_handler is False
    assert sent[0]["status"] == 413
    assert b"assistant_request_too_large" in sent[1]["body"]
    assert b"secret" not in sent[1]["body"]
    assert body_reads == (0 if headers else 2)
