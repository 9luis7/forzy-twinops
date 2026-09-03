"""Preview-only administrative HTTP surface for RAG corpora."""

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from twinops.api.v2_routes import PUBLIC_ASSET_ID
from twinops.rag.chunking import ChunkingLimitError
from twinops.rag.admin_service import DuplicateDocumentError
from twinops.rag.embeddings import EmbeddingGatewayError
from twinops.rag.errors import (
    CorpusCompatibilityError,
    CorpusConflictError,
    CorpusNotFoundError,
    InvalidAdminInputError,
)
from twinops.rag.models import DocumentMetadata
from twinops.rag.pdf import (
    MAX_PDF_BYTES,
    PdfContentLimitError,
    PdfPayloadTooLargeError,
    PdfValidationError,
)


class CreateCorpusRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    asset_id: str = Field(alias="assetId", min_length=1, max_length=120)
    chunk_target_tokens: int = Field(700, alias="chunkTargetTokens", ge=200, le=2_000)
    chunk_overlap_tokens: int = Field(100, alias="chunkOverlapTokens", ge=0, le=500)
    min_relevance_score: float = Field(0.0, alias="minRelevanceScore", ge=0, le=1)


class RetrievalTestRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(6, ge=1, le=12)


def create_rag_admin_router() -> APIRouter:
    router = APIRouter(prefix="/api/v2/admin/rag", tags=["rag-admin"])

    @router.post("/corpora", status_code=201)
    def create_corpus(request: Request, body: CreateCorpusRequest):
        service = _require_admin(request)
        if body.asset_id != PUBLIC_ASSET_ID:
            raise HTTPException(status_code=404, detail="asset_not_found")
        try:
            corpus = service.create_draft(
                asset_id=body.asset_id,
                chunk_target_tokens=body.chunk_target_tokens,
                chunk_overlap_tokens=body.chunk_overlap_tokens,
                min_relevance_score=body.min_relevance_score,
            )
        except InvalidAdminInputError as exc:
            raise HTTPException(
                status_code=422, detail=str(exc)
            ) from None
        return _corpus_json(corpus)

    @router.post("/corpora/{corpus_id}/documents", status_code=201)
    async def upload_document(
        request: Request,
        corpus_id: str,
        file: Annotated[UploadFile, File()],
        manufacturer: Annotated[str, Form()],
        equipment_model: Annotated[str, Form(alias="equipmentModel")],
        revision: Annotated[str, Form()],
        language: Annotated[str, Form()],
        source_url: Annotated[str, Form(alias="sourceUrl")],
    ):
        service = _require_admin(request)
        try:
            payload = await file.read(MAX_PDF_BYTES + 1)
        finally:
            await file.close()
        try:
            result = await service.upload_document(
                corpus_id,
                filename=file.filename or "",
                content_type=file.content_type,
                payload=payload,
                metadata=DocumentMetadata(
                    manufacturer=manufacturer,
                    equipment_model=equipment_model,
                    revision=revision,
                    language=language,
                    source_url=source_url,
                ),
            )
        except ValidationError:
            raise HTTPException(
                status_code=422, detail="invalid_document_metadata"
            ) from None
        except DuplicateDocumentError:
            raise HTTPException(status_code=409, detail="duplicate_document") from None
        except CorpusNotFoundError:
            raise HTTPException(status_code=404, detail="corpus_not_found") from None
        except InvalidAdminInputError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except CorpusCompatibilityError:
            raise HTTPException(status_code=409, detail="corpus_incompatible") from None
        except CorpusConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except PdfPayloadTooLargeError:
            raise HTTPException(status_code=413, detail="pdf_too_large") from None
        except (PdfContentLimitError, ChunkingLimitError):
            raise HTTPException(
                status_code=422, detail="document_content_too_large"
            ) from None
        except PdfValidationError:
            raise HTTPException(status_code=422, detail="invalid_pdf") from None
        except EmbeddingGatewayError:
            raise HTTPException(
                status_code=503, detail="embedding_gateway_unavailable"
            ) from None
        return {
            "document": _document_json(result.document),
            "coverage": _coverage_json(result.coverage),
        }

    @router.get("/corpora/{corpus_id}")
    def get_coverage(request: Request, corpus_id: str):
        service = _require_admin(request)
        try:
            coverage = service.coverage(corpus_id)
            corpus = service.repository.get_corpus(corpus_id)
            assert corpus is not None
        except CorpusNotFoundError:
            raise HTTPException(status_code=404, detail="corpus_not_found") from None
        return {"corpus": _corpus_json(corpus), "coverage": _coverage_json(coverage)}

    @router.post("/corpora/{corpus_id}/retrieval-test")
    async def retrieval_test(
        request: Request, corpus_id: str, body: RetrievalTestRequest
    ):
        service = _require_admin(request)
        try:
            results = await service.test_retrieval(
                corpus_id, body.query, limit=body.limit
            )
        except CorpusNotFoundError:
            raise HTTPException(status_code=404, detail="corpus_not_found") from None
        except InvalidAdminInputError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except CorpusCompatibilityError:
            raise HTTPException(status_code=409, detail="corpus_incompatible") from None
        except EmbeddingGatewayError:
            raise HTTPException(
                status_code=503, detail="embedding_gateway_unavailable"
            ) from None
        return {"items": [_chunk_json(item) for item in results]}

    @router.post("/corpora/{corpus_id}/publish")
    def publish(request: Request, corpus_id: str):
        service = _require_admin(request)
        try:
            return _activation_json(service.publish(corpus_id))
        except CorpusNotFoundError:
            raise HTTPException(status_code=404, detail="corpus_not_found") from None
        except (CorpusConflictError, CorpusCompatibilityError):
            raise HTTPException(
                status_code=409, detail="corpus_not_publishable"
            ) from None

    @router.post("/corpora/{corpus_id}/reactivate")
    def reactivate(request: Request, corpus_id: str):
        service = _require_admin(request)
        try:
            return _activation_json(service.reactivate(corpus_id))
        except CorpusNotFoundError:
            raise HTTPException(status_code=404, detail="corpus_not_found") from None
        except (CorpusConflictError, CorpusCompatibilityError):
            raise HTTPException(
                status_code=409, detail="corpus_not_reactivatable"
            ) from None

    return router


def _require_admin(request: Request):
    settings = request.app.state.settings
    if not (
        settings.vercel_environment == "preview" and settings.rag_admin_enabled
    ):
        raise HTTPException(status_code=404, detail="not_found")
    service = request.app.state.rag_admin_service
    if service is None:
        raise HTTPException(status_code=503, detail="rag_admin_unavailable")
    return service


def _corpus_json(item):
    return {
        "corpusId": item.corpus_id,
        "assetId": item.asset_id,
        "manufacturer": item.manufacturer,
        "equipmentModel": item.equipment_model,
        "status": item.status,
        "embeddingModel": item.embedding_model,
        "embeddingDimensions": item.embedding_dimensions,
        "chunkTargetTokens": item.chunk_target_tokens,
        "chunkOverlapTokens": item.chunk_overlap_tokens,
        "minRelevanceScore": item.min_relevance_score,
    }


def _document_json(item):
    return {
        "documentId": item.document_id,
        "corpusId": item.corpus_id,
        "manufacturer": item.manufacturer,
        "equipmentModel": item.equipment_model,
        "revision": item.revision,
        "language": item.language,
        "sourceUrl": item.source_url,
        "sha256": item.sha256,
        "pageCount": item.page_count,
        "coveragePages": item.coverage_pages,
    }


def _coverage_json(item):
    return {
        "corpusId": item.corpus_id,
        "documentCount": item.document_count,
        "pageCount": item.page_count,
        "coveragePages": item.coverage_pages,
        "chunkCount": item.chunk_count,
    }


def _chunk_json(item):
    return {
        "chunkId": item.chunk_id,
        "documentId": item.document_id,
        "pageStart": item.page_start,
        "pageEnd": item.page_end,
        "section": item.section,
        "excerpt": item.text[:500],
        "contentHash": item.content_hash,
    }


def _activation_json(item):
    return {
        "assetId": item.asset_id,
        "corpusId": item.corpus_id,
        "previousCorpusId": item.previous_corpus_id,
        "activatedAt": item.activated_at.isoformat(),
    }
