import httpx
import pytest

from twinops.rag import pdf as rag_pdf


SOURCE_URL = "https://static.weg.net/manual.pdf"


def _fetcher(http):
    fetcher_type = getattr(rag_pdf, "OfficialPdfSourceFetcher", None)
    assert fetcher_type is not None, "official PDF source fetcher is missing"
    return fetcher_type(http, timeout_seconds=1)


@pytest.mark.asyncio
async def test_official_pdf_source_fetcher_streams_a_bounded_weg_pdf():
    payload = b"%PDF-1.4\nsearchable"

    def handler(request):
        assert str(request.url) == SOURCE_URL
        return httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=payload,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        fetched = await _fetcher(http).fetch(SOURCE_URL)

    assert fetched == (payload, "application/pdf", "manual.pdf")


@pytest.mark.asyncio
async def test_official_pdf_source_fetcher_rejects_non_allowlisted_hosts_before_io():
    def forbidden_io(request):
        raise AssertionError("non-allowlisted source must not reach the network")

    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden_io)) as http:
        with pytest.raises(ValueError):
            await _fetcher(http).fetch("https://127.0.0.1/manual.pdf")


@pytest.mark.asyncio
async def test_official_pdf_source_fetcher_rejects_oversized_or_redirected_responses():
    responses = iter(
        (
            httpx.Response(
                200,
                headers={
                    "content-type": "application/pdf",
                    "content-length": str(rag_pdf.MAX_PDF_BYTES + 1),
                },
                content=b"",
            ),
            httpx.Response(302, headers={"location": "https://example.com/manual.pdf"}),
        )
    )

    async def handler(request):
        return next(responses)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        fetcher = _fetcher(http)
        with pytest.raises(rag_pdf.PdfPayloadTooLargeError):
            await fetcher.fetch(SOURCE_URL)
        with pytest.raises(ValueError):
            await fetcher.fetch(SOURCE_URL)
