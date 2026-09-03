from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from twinops.config_v2 import SettingsV2
from twinops.main_v2 import create_app_v2
from twinops.rag.admin_service import RagAdminService
from twinops.rag.embeddings import EmbeddingGatewayError
from twinops.rag.repository import InMemoryRagRepository
from twinops.rag.request_limits import MAX_UPLOAD_REQUEST_BYTES


def searchable_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    bodies = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length "
        + str(len(stream)).encode("ascii")
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(bodies, start=1):
        offsets.append(len(result))
        result.extend(f"{number} 0 obj\n".encode("ascii"))
        result.extend(body + b"\nendobj\n")
    xref_offset = len(result)
    result.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    result.extend(
        f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(result)


class _Repository:
    def latest(self, asset_id):
        return []

    def health(self, sensor_id):
        return None


class _Refresh:
    async def refresh(self, now):
        raise AssertionError("must not refresh")


class _Embeddings:
    model = "embed-v1"
    dimensions = 3

    def __init__(self, *, failure=None):
        self.failure = failure
        self.calls = []

    async def embed(self, texts):
        self.calls.append(tuple(texts))
        if self.failure is not None:
            raise self.failure
        return tuple((0.1, 0.2, 0.3) for _ in texts)


def _client(*, environment, enabled, embeddings=None):
    settings = SettingsV2(
        upstream_base_url="https://upstream.invalid",
        vercel_environment=environment,
        rag_admin_enabled=enabled,
        rag_manufacturer="WEG",
        rag_equipment_model="W22",
    )
    service = RagAdminService(
        InMemoryRagRepository(),
        embeddings or _Embeddings(),
        manufacturer="WEG",
        equipment_model="W22",
    )
    app = create_app_v2(
        repository=_Repository(),
        settings=settings,
        refresh_service=_Refresh(),
        assessment_scorer=None,
        clock=lambda: datetime(2026, 9, 3, tzinfo=timezone.utc),
        rag_admin_service=service,
    )
    return TestClient(app)


def test_admin_routes_are_always_404_in_production_even_when_flag_is_true():
    response = _client(environment="production", enabled=True).post(
        "/api/v2/admin/rag/corpora",
        json={"assetId": "forzy-motor-01"},
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/v2/admin/rag/corpora"),
        ("post", "/api/v2/admin/rag/corpora/c1/documents"),
        ("get", "/api/v2/admin/rag/corpora/c1"),
        ("post", "/api/v2/admin/rag/corpora/c1/retrieval-test"),
        ("post", "/api/v2/admin/rag/corpora/c1/publish"),
        ("post", "/api/v2/admin/rag/corpora/c1/reactivate"),
    ],
)
def test_every_admin_route_returns_404_before_payload_validation_in_production(
    method, path
):
    response = getattr(_client(environment="production", enabled=True), method)(
        path
    )

    assert response.status_code == 404


def test_admin_routes_are_404_in_preview_when_flag_is_false():
    response = _client(environment="preview", enabled=False).post(
        "/api/v2/admin/rag/corpora",
        json={"assetId": "forzy-motor-01"},
    )

    assert response.status_code == 404


def test_admin_draft_creation_is_available_only_in_enabled_preview():
    response = _client(environment="preview", enabled=True).post(
        "/api/v2/admin/rag/corpora",
        json={"assetId": "forzy-motor-01"},
    )

    assert response.status_code == 201
    assert response.json()["assetId"] == "forzy-motor-01"
    assert response.json()["status"] == "draft"


def test_admin_cannot_expand_v1_beyond_the_canonical_asset():
    response = _client(environment="preview", enabled=True).post(
        "/api/v2/admin/rag/corpora",
        json={"assetId": "other-motor"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "asset_not_found"}


def test_admin_rejects_invalid_chunk_configuration_without_internal_error():
    response = _client(environment="preview", enabled=True).post(
        "/api/v2/admin/rag/corpora",
        json={
            "assetId": "forzy-motor-01",
            "chunkTargetTokens": 200,
            "chunkOverlapTokens": 200,
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_corpus_configuration"}


def test_non_preview_environment_cannot_enable_admin():
    response = _client(environment="development", enabled=True).post(
        "/api/v2/admin/rag/corpora",
        json={"assetId": "forzy-motor-01"},
    )

    assert response.status_code == 404


def test_enabled_preview_can_upload_and_inspect_a_draft_without_activating_it():
    client = _client(environment="preview", enabled=True)
    created = client.post(
        "/api/v2/admin/rag/corpora",
        json={"assetId": "forzy-motor-01"},
    ).json()
    corpus_id = created["corpusId"]

    response = client.post(
        f"/api/v2/admin/rag/corpora/{corpus_id}/documents",
        files={
            "file": (
                "manual.pdf",
                searchable_pdf("MAINTENANCE bearing lubrication"),
                "application/pdf",
            )
        },
        data={
            "manufacturer": "WEG",
            "equipmentModel": "W22",
            "revision": "2026-01",
            "language": "en",
            "sourceUrl": "https://manufacturer.example/manual.pdf",
        },
    )

    assert response.status_code == 201
    assert response.json()["coverage"]["coveragePages"] == 1
    inspection = client.get(f"/api/v2/admin/rag/corpora/{corpus_id}")
    assert inspection.json()["corpus"]["status"] == "draft"


def test_upload_rejects_invalid_metadata_with_422_and_duplicate_with_409():
    client = _client(environment="preview", enabled=True)
    corpus_id = client.post(
        "/api/v2/admin/rag/corpora",
        json={"assetId": "forzy-motor-01"},
    ).json()["corpusId"]
    payload = searchable_pdf("searchable manual")
    form = {
        "manufacturer": "WEG",
        "equipmentModel": "W22",
        "revision": "2026-01",
        "language": "en",
        "sourceUrl": "https://manufacturer.example/manual.pdf",
    }

    invalid = client.post(
        f"/api/v2/admin/rag/corpora/{corpus_id}/documents",
        files={"file": ("manual.pdf", payload, "application/pdf")},
        data={**form, "manufacturer": "   "},
    )
    accepted = client.post(
        f"/api/v2/admin/rag/corpora/{corpus_id}/documents",
        files={"file": ("manual.pdf", payload, "application/pdf")},
        data=form,
    )
    duplicate = client.post(
        f"/api/v2/admin/rag/corpora/{corpus_id}/documents",
        files={"file": ("copy.pdf", payload, "application/pdf")},
        data=form,
    )

    assert invalid.status_code == 422
    assert accepted.status_code == 201
    assert duplicate.status_code == 409


def test_publish_and_reactivate_domain_conflicts_are_sanitized():
    client = _client(environment="preview", enabled=True)
    corpus_id = client.post(
        "/api/v2/admin/rag/corpora",
        json={"assetId": "forzy-motor-01"},
    ).json()["corpusId"]

    publish_empty = client.post(
        f"/api/v2/admin/rag/corpora/{corpus_id}/publish"
    )
    reactivate_draft = client.post(
        f"/api/v2/admin/rag/corpora/{corpus_id}/reactivate"
    )

    assert publish_empty.status_code == 409
    assert publish_empty.json() == {"detail": "corpus_not_publishable"}
    assert reactivate_draft.status_code == 409
    assert reactivate_draft.json() == {"detail": "corpus_not_reactivatable"}


def _new_corpus(client):
    return client.post(
        "/api/v2/admin/rag/corpora",
        json={"assetId": "forzy-motor-01"},
    ).json()["corpusId"]


def _manual_form():
    return {
        "manufacturer": "WEG",
        "equipmentModel": "W22",
        "revision": "2026-01",
        "language": "en",
        "sourceUrl": "https://manufacturer.example/manual.pdf",
    }


def test_upload_invalid_extension_is_422_and_published_corpus_is_409():
    client = _client(environment="preview", enabled=True)
    corpus_id = _new_corpus(client)
    payload = searchable_pdf("searchable manual")

    invalid = client.post(
        f"/api/v2/admin/rag/corpora/{corpus_id}/documents",
        files={"file": ("manual.txt", payload, "application/pdf")},
        data=_manual_form(),
    )
    accepted = client.post(
        f"/api/v2/admin/rag/corpora/{corpus_id}/documents",
        files={"file": ("manual.pdf", payload, "application/pdf")},
        data=_manual_form(),
    )
    published = client.post(
        f"/api/v2/admin/rag/corpora/{corpus_id}/publish"
    )
    immutable = client.post(
        f"/api/v2/admin/rag/corpora/{corpus_id}/documents",
        files={
            "file": (
                "manual-v2.pdf",
                searchable_pdf("different searchable manual"),
                "application/pdf",
            )
        },
        data={**_manual_form(), "revision": "2026-02"},
    )

    assert invalid.status_code == 422
    assert invalid.json() == {"detail": "invalid_document_filename"}
    assert accepted.status_code == 201
    assert published.status_code == 200
    assert immutable.status_code == 409
    assert immutable.json() == {"detail": "corpus_immutable"}


def test_missing_retrieval_is_404_without_gateway_call():
    embeddings = _Embeddings()
    client = _client(
        environment="preview", enabled=True, embeddings=embeddings
    )

    response = client.post(
        "/api/v2/admin/rag/corpora/missing/retrieval-test",
        json={"query": "bearing", "limit": 6},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "corpus_not_found"}
    assert embeddings.calls == []


def test_gateway_failure_is_503_without_provider_detail_leakage():
    embeddings = _Embeddings(
        failure=EmbeddingGatewayError("private manual timed out")
    )
    client = _client(
        environment="preview", enabled=True, embeddings=embeddings
    )
    corpus_id = _new_corpus(client)

    response = client.post(
        f"/api/v2/admin/rag/corpora/{corpus_id}/retrieval-test",
        json={"query": "bearing", "limit": 6},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "embedding_gateway_unavailable"}
    assert "private manual" not in response.text


def test_oversized_multipart_upload_is_413_before_route_parsing():
    client = _client(environment="preview", enabled=True)
    corpus_id = _new_corpus(client)
    oversized = b"%PDF-" + b"x" * MAX_UPLOAD_REQUEST_BYTES

    response = client.post(
        f"/api/v2/admin/rag/corpora/{corpus_id}/documents",
        files={"file": ("manual.pdf", oversized, "application/pdf")},
        data=_manual_form(),
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "upload_request_too_large"}
