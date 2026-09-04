"""Bounded, in-memory extraction of searchable PDF text."""

from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
import re
from urllib.parse import unquote, urlsplit

import httpx
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from twinops.rag.models import ExtractedPage, ExtractedPdf


MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_PDF_PAGES = 400
# These caps admit ordinary technical manuals while bounding decompression and
# parser expansion before any embedding request is made.
MAX_EXTRACTED_CHARS_PER_PAGE = 500_000
MAX_EXTRACTED_CHARS_TOTAL = 4_000_000


class PdfValidationError(ValueError):
    pass


class PdfContentLimitError(PdfValidationError):
    pass


class PdfPayloadTooLargeError(PdfValidationError):
    pass


class PdfSourceFetchError(ValueError):
    pass


class PdfSourceUnavailableError(RuntimeError):
    pass


class OfficialPdfSourceFetcher:
    """Fetch one allowlisted manufacturer PDF without persisting its bytes."""

    def __init__(self, http: httpx.AsyncClient, *, timeout_seconds: float = 10) -> None:
        if timeout_seconds <= 0:
            raise ValueError("source fetch timeout must be positive")
        self.http = http
        self.timeout_seconds = timeout_seconds

    async def fetch(self, source_url: str) -> tuple[bytes, str, str]:
        filename = _validate_official_source_url(source_url)
        try:
            async with self.http.stream(
                "GET",
                source_url,
                headers={"Accept": "application/pdf"},
                follow_redirects=False,
                timeout=self.timeout_seconds,
            ) as response:
                if response.status_code != 200:
                    raise PdfSourceFetchError("official PDF source returned non-200")
                content_type = (
                    response.headers.get("content-type", "")
                    .split(";", 1)[0]
                    .strip()
                    .lower()
                )
                if content_type != "application/pdf":
                    raise PdfSourceFetchError("official PDF source returned invalid mime")
                content_length = response.headers.get("content-length")
                if content_length is not None:
                    try:
                        declared_size = int(content_length)
                    except ValueError:
                        raise PdfSourceFetchError(
                            "official PDF source returned invalid length"
                        ) from None
                    if declared_size < 0:
                        raise PdfSourceFetchError(
                            "official PDF source returned invalid length"
                        )
                    if declared_size > MAX_PDF_BYTES:
                        raise PdfPayloadTooLargeError("PDF exceeds 25 MiB")
                payload = bytearray()
                async for chunk in response.aiter_bytes():
                    payload.extend(chunk)
                    if len(payload) > MAX_PDF_BYTES:
                        raise PdfPayloadTooLargeError("PDF exceeds 25 MiB")
        except (PdfPayloadTooLargeError, PdfSourceFetchError):
            raise
        except httpx.RequestError:
            raise PdfSourceUnavailableError("official PDF source unavailable") from None
        return bytes(payload), content_type, filename


def _validate_official_source_url(source_url: str) -> str:
    try:
        parsed = urlsplit(source_url)
        port = parsed.port
    except (TypeError, ValueError):
        raise PdfSourceFetchError("invalid official PDF source") from None
    if (
        parsed.scheme != "https"
        or parsed.hostname != "static.weg.net"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in {None, 443}
    ):
        raise PdfSourceFetchError("invalid official PDF source")
    filename = unquote(PurePosixPath(parsed.path).name)
    if (
        not filename.casefold().endswith(".pdf")
        or any(ord(character) <= 0x20 or ord(character) == 0x7F for character in filename)
    ):
        raise PdfSourceFetchError("invalid official PDF filename")
    return filename


def extract_searchable_pdf(
    payload: bytes, *, content_type: str | None
) -> ExtractedPdf:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if media_type != "application/pdf":
        raise PdfValidationError("invalid PDF mime type")
    if len(payload) > MAX_PDF_BYTES:
        raise PdfPayloadTooLargeError("PDF exceeds 25 MiB")
    if not payload.startswith(b"%PDF-"):
        raise PdfValidationError("invalid PDF signature")

    try:
        reader = PdfReader(BytesIO(payload), strict=True)
        if reader.is_encrypted:
            raise PdfValidationError("encrypted PDFs are not supported")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise PdfValidationError("PDF exceeds 400 pages")
        extracted_pages: list[ExtractedPage] = []
        total_characters = 0
        for index, page in enumerate(reader.pages, start=1):
            text = _normalize_text(page.extract_text() or "")
            if len(text) > MAX_EXTRACTED_CHARS_PER_PAGE:
                raise PdfContentLimitError("PDF page text exceeds character limit")
            total_characters += len(text)
            if total_characters > MAX_EXTRACTED_CHARS_TOTAL:
                raise PdfContentLimitError("PDF total text exceeds character limit")
            extracted_pages.append(ExtractedPage(page_number=index, text=text))
        pages = tuple(extracted_pages)
    except PdfValidationError:
        raise
    except (PdfReadError, ValueError, TypeError, OSError):
        raise PdfValidationError("invalid PDF structure") from None

    coverage = sum(bool(page.text) for page in pages)
    if coverage == 0:
        raise PdfValidationError("PDF has no searchable text")
    return ExtractedPdf(
        sha256=sha256(payload).hexdigest(),
        pages=pages,
        page_count=len(pages),
        coverage_pages=coverage,
    )


def _normalize_text(value: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line)
