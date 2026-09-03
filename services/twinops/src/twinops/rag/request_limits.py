"""ASGI request-size guard that runs before multipart parsing/spooling."""

from starlette.responses import JSONResponse

from twinops.rag.pdf import MAX_PDF_BYTES


# Allows bounded multipart metadata and framing in addition to the 25 MiB PDF.
MAX_UPLOAD_REQUEST_BYTES = MAX_PDF_BYTES + 64 * 1024
_UPLOAD_PREFIX = "/api/v2/admin/rag/corpora/"
_UPLOAD_SUFFIX = "/documents"


class RagAdminUploadLimitMiddleware:
    def __init__(self, app, *, max_bytes: int = MAX_UPLOAD_REQUEST_BYTES) -> None:
        if max_bytes <= 0:
            raise ValueError("request body limit must be positive")
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if not _is_upload(scope):
            await self.app(scope, receive, send)
            return

        declared = _content_length(scope)
        if declared is not None and declared > self.max_bytes:
            await _too_large_response(scope, receive, send)
            return

        buffered = []
        received = 0
        while True:
            message = await receive()
            buffered.append(message)
            if message.get("type") != "http.request":
                break
            received += len(message.get("body", b""))
            if received > self.max_bytes:
                await _too_large_response(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        iterator = iter(buffered)

        async def replay_receive():
            try:
                return next(iterator)
            except StopIteration:
                return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)


def _is_upload(scope) -> bool:
    path = scope.get("path", "")
    return (
        scope.get("type") == "http"
        and scope.get("method") == "POST"
        and path.startswith(_UPLOAD_PREFIX)
        and path.endswith(_UPLOAD_SUFFIX)
    )


def _content_length(scope) -> int | None:
    for raw_name, raw_value in scope.get("headers", ()):
        if raw_name.lower() == b"content-length":
            try:
                value = int(raw_value)
            except (TypeError, ValueError):
                return None
            return value if value >= 0 else None
    return None


async def _too_large_response(scope, receive, send) -> None:
    response = JSONResponse(
        status_code=413,
        content={"detail": "upload_request_too_large"},
    )
    await response(scope, receive, send)
