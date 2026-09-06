import pytest

from twinops.rag.models import DocumentMetadata
from twinops.rag.pdf import (
    MAX_EXTRACTED_CHARS_PER_PAGE,
    MAX_EXTRACTED_CHARS_TOTAL,
    MAX_PDF_BYTES,
    PdfContentLimitError,
    PdfValidationError,
    extract_searchable_pdf,
)

from .pdf_factory import searchable_pdf


def _metadata(**overrides):
    values = {
        "manufacturer": "WEG",
        "equipment_model": "W22",
        "revision": "2026-01",
        "language": "en",
        "source_url": "https://manufacturer.example/manual.pdf",
    }
    values.update(overrides)
    return DocumentMetadata(**values)


@pytest.mark.parametrize(
    "field",
    ["manufacturer", "equipment_model", "revision", "language", "source_url"],
)
def test_document_metadata_requires_all_provenance_fields(field):
    values = _metadata().model_dump()
    values[field] = ""

    with pytest.raises(ValueError):
        DocumentMetadata(**values)


def test_document_metadata_requires_https_source_url():
    with pytest.raises(ValueError, match="https"):
        _metadata(source_url="http://manufacturer.example/manual.pdf")


@pytest.mark.parametrize(
    ("content_type", "payload", "message"),
    [
        ("application/octet-stream", b"%PDF-1.4\n", "mime"),
        ("application/pdf", b"not a pdf", "signature"),
        ("application/pdf", b" %PDF-1.4\n", "signature"),
    ],
)
def test_pdf_requires_exact_mime_and_leading_signature(
    content_type, payload, message
):
    with pytest.raises(PdfValidationError, match=message):
        extract_searchable_pdf(payload, content_type=content_type)


def test_pdf_rejects_payload_above_25_mib_before_parsing():
    payload = b"%PDF-" + b"x" * (MAX_PDF_BYTES - 4)

    with pytest.raises(PdfValidationError, match="25 MiB"):
        extract_searchable_pdf(payload, content_type="application/pdf")


def test_pdf_accepts_400_pages_and_rejects_401_pages():
    accepted = extract_searchable_pdf(
        searchable_pdf(*(["searchable"] * 400)),
        content_type="application/pdf",
    )
    assert len(accepted.pages) == 400

    with pytest.raises(PdfValidationError, match="400 pages"):
        extract_searchable_pdf(
            searchable_pdf(*(["searchable"] * 401)),
            content_type="application/pdf",
        )


def test_pdf_extracts_searchable_text_page_by_page_and_hashes_original():
    payload = searchable_pdf("Safety section", "Lubrication interval")

    result = extract_searchable_pdf(payload, content_type="application/pdf")

    assert [page.page_number for page in result.pages] == [1, 2]
    assert [page.text for page in result.pages] == [
        "Safety section",
        "Lubrication interval",
    ]
    assert len(result.sha256) == 64
    assert result.coverage_pages == 2


def test_pdf_rejects_document_without_searchable_text():
    with pytest.raises(PdfValidationError, match="searchable text"):
        extract_searchable_pdf(
            searchable_pdf("", "   "),
            content_type="application/pdf",
        )


class _ExpandedPage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class _ExpandedReader:
    is_encrypted = False

    def __init__(self, _, *, strict):
        self.pages = [_ExpandedPage("x" * (MAX_EXTRACTED_CHARS_PER_PAGE + 1))]


def test_pdf_rejects_highly_expanded_page_before_retaining_extracted_document(
    monkeypatch,
):
    monkeypatch.setattr("twinops.rag.pdf.PdfReader", _ExpandedReader)

    with pytest.raises(PdfContentLimitError, match="page text"):
        extract_searchable_pdf(b"%PDF-small", content_type="application/pdf")


class _ExpandedTotalReader:
    is_encrypted = False

    def __init__(self, _, *, strict):
        page = "x" * (MAX_EXTRACTED_CHARS_TOTAL // 20 + 1)
        self.pages = [_ExpandedPage(page) for _ in range(20)]


def test_pdf_rejects_total_extracted_text_expansion(monkeypatch):
    monkeypatch.setattr("twinops.rag.pdf.PdfReader", _ExpandedTotalReader)

    with pytest.raises(PdfContentLimitError, match="total text"):
        extract_searchable_pdf(b"%PDF-small", content_type="application/pdf")
