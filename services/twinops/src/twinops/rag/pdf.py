"""Bounded, in-memory extraction of searchable PDF text."""

from hashlib import sha256
from io import BytesIO
import re

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
