"""Repository protocol plus in-memory and PostgreSQL implementations."""

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
import json
import math
from threading import RLock
from typing import Protocol

import psycopg
from psycopg.rows import dict_row

from twinops.rag.models import (
    ActiveCorpusChange,
    CorpusCoverage,
    RagChunk,
    RagCorpus,
    RagDocument,
)


class RagRepository(Protocol):
    def create_corpus(self, corpus: RagCorpus) -> RagCorpus: ...
    def get_corpus(self, corpus_id: str) -> RagCorpus | None: ...
    def find_document_by_sha256(
        self, corpus_id: str, sha256: str
    ) -> RagDocument | None: ...
    def add_document(
        self, document: RagDocument, chunks: Sequence[RagChunk]
    ) -> None: ...
    def coverage(self, corpus_id: str) -> CorpusCoverage: ...
    def preview_search(
        self,
        corpus_id: str,
        *,
        query: str,
        query_embedding: Sequence[float],
        limit: int,
    ) -> list[RagChunk]: ...
    def publish_corpus(
        self, asset_id: str, corpus_id: str
    ) -> ActiveCorpusChange: ...
    def activate_published_corpus(
        self, asset_id: str, corpus_id: str
    ) -> ActiveCorpusChange: ...
    def get_active_corpus(self, asset_id: str) -> RagCorpus | None: ...


class InMemoryRagRepository:
    def __init__(self) -> None:
        self._corpora: dict[str, RagCorpus] = {}
        self._documents: dict[str, RagDocument] = {}
        self._chunks: dict[str, RagChunk] = {}
        self._active: dict[str, str] = {}
        self._lock = RLock()

    def create_corpus(self, corpus: RagCorpus) -> RagCorpus:
        with self._lock:
            if corpus.corpus_id in self._corpora:
                raise ValueError("corpus already exists")
            self._corpora[corpus.corpus_id] = corpus
        return corpus

    def get_corpus(self, corpus_id: str) -> RagCorpus | None:
        return self._corpora.get(corpus_id)

    def find_document_by_sha256(
        self, corpus_id: str, sha256: str
    ) -> RagDocument | None:
        return next(
            (
                item
                for item in self._documents.values()
                if item.corpus_id == corpus_id and item.sha256 == sha256
            ),
            None,
        )

    def add_document(
        self, document: RagDocument, chunks: Sequence[RagChunk]
    ) -> None:
        with self._lock:
            corpus = self._require_draft(document.corpus_id)
            if (
                self.find_document_by_sha256(
                    document.corpus_id, document.sha256
                )
                is not None
            ):
                raise ValueError("duplicate document sha256")
            if document.document_id in self._documents:
                raise ValueError("document already exists")
            if (
                document.manufacturer != corpus.manufacturer
                or document.equipment_model != corpus.equipment_model
            ):
                raise ValueError("document identity does not match corpus")
            seen_ordinals: set[int] = set()
            for chunk in chunks:
                if (
                    chunk.corpus_id != corpus.corpus_id
                    or chunk.document_id != document.document_id
                ):
                    raise ValueError("chunk corpus/document isolation violation")
                _validated_vector(
                    chunk.embedding, corpus.embedding_dimensions
                )
                if chunk.ordinal in seen_ordinals or chunk.chunk_id in self._chunks:
                    raise ValueError("duplicate chunk identity")
                seen_ordinals.add(chunk.ordinal)
            self._documents[document.document_id] = document
            self._chunks.update((chunk.chunk_id, chunk) for chunk in chunks)

    def coverage(self, corpus_id: str) -> CorpusCoverage:
        if corpus_id not in self._corpora:
            raise KeyError("corpus not found")
        documents = [
            item for item in self._documents.values() if item.corpus_id == corpus_id
        ]
        chunks = [item for item in self._chunks.values() if item.corpus_id == corpus_id]
        return CorpusCoverage(
            corpus_id=corpus_id,
            document_count=len(documents),
            page_count=sum(item.page_count for item in documents),
            coverage_pages=sum(item.coverage_pages for item in documents),
            chunk_count=len(chunks),
        )

    def preview_search(
        self,
        corpus_id: str,
        *,
        query: str,
        query_embedding: Sequence[float],
        limit: int,
    ) -> list[RagChunk]:
        corpus = self._require_corpus(corpus_id)
        _validated_vector(query_embedding, corpus.embedding_dimensions)
        terms = {term.casefold() for term in query.split() if term}
        candidates = [
            item for item in self._chunks.values() if item.corpus_id == corpus_id
        ]

        def score(item: RagChunk) -> tuple[float, float, int, str]:
            lexical = sum(term in item.text.casefold() for term in terms)
            distance = _cosine_distance(item.embedding, query_embedding)
            return (-float(lexical), distance, item.ordinal, item.chunk_id)

        return sorted(candidates, key=score)[:limit]

    def publish_corpus(
        self, asset_id: str, corpus_id: str
    ) -> ActiveCorpusChange:
        with self._lock:
            corpus = self._require_corpus(corpus_id)
            if corpus.asset_id != asset_id:
                raise ValueError("corpus asset does not match activation asset")
            if corpus.status != "draft":
                raise ValueError("only a draft corpus can be published")
            if not any(
                item.corpus_id == corpus_id for item in self._documents.values()
            ):
                raise ValueError("cannot publish an empty corpus")
            if any(
                item.corpus_id == corpus_id
                and (
                    item.manufacturer != corpus.manufacturer
                    or item.equipment_model != corpus.equipment_model
                )
                for item in self._documents.values()
            ):
                raise ValueError("corpus contains incompatible document identity")
            corpus = corpus.published()
            self._corpora[corpus_id] = corpus
            return self._activate(asset_id, corpus_id)

    def activate_published_corpus(
        self, asset_id: str, corpus_id: str
    ) -> ActiveCorpusChange:
        with self._lock:
            corpus = self._require_corpus(corpus_id)
            if corpus.asset_id != asset_id:
                raise ValueError("corpus asset does not match activation asset")
            if corpus.status != "published":
                raise ValueError("only a published corpus can be reactivated")
            return self._activate(asset_id, corpus_id)

    def get_active_corpus(self, asset_id: str) -> RagCorpus | None:
        corpus_id = self._active.get(asset_id)
        return None if corpus_id is None else self._corpora[corpus_id]

    def _activate(self, asset_id: str, corpus_id: str) -> ActiveCorpusChange:
        previous = self._active.get(asset_id)
        self._active[asset_id] = corpus_id
        return ActiveCorpusChange(
            asset_id=asset_id,
            corpus_id=corpus_id,
            previous_corpus_id=previous,
            activated_at=datetime.now(timezone.utc),
        )

    def _require_corpus(self, corpus_id: str) -> RagCorpus:
        corpus = self._corpora.get(corpus_id)
        if corpus is None:
            raise KeyError("corpus not found")
        return corpus

    def _require_draft(self, corpus_id: str) -> RagCorpus:
        corpus = self._require_corpus(corpus_id)
        if corpus.status != "draft":
            raise ValueError("published corpora are immutable")
        return corpus


class PostgresRagRepository:
    """pgvector repository. Schema lifecycle remains an external gate."""

    def __init__(
        self,
        database_url: str,
        *,
        connection_factory: Callable[[], object] | None = None,
    ) -> None:
        self._database_url = database_url
        self._connection_factory = connection_factory

    def _connection(self):
        if self._connection_factory is not None:
            return self._connection_factory()
        return psycopg.connect(self._database_url, row_factory=dict_row)

    def create_corpus(self, corpus: RagCorpus) -> RagCorpus:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO rag_corpora (corpus_id,asset_id,manufacturer,"
                "equipment_model,status,embedding_model,"
                "embedding_dimensions,chunk_target_tokens,chunk_overlap_tokens,"
                "min_relevance_score,created_at) VALUES "
                "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    corpus.corpus_id,
                    corpus.asset_id,
                    corpus.manufacturer,
                    corpus.equipment_model,
                    corpus.status,
                    corpus.embedding_model,
                    corpus.embedding_dimensions,
                    corpus.chunk_target_tokens,
                    corpus.chunk_overlap_tokens,
                    corpus.min_relevance_score,
                    corpus.created_at,
                ),
            )
        return corpus

    def get_corpus(self, corpus_id: str) -> RagCorpus | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM rag_corpora WHERE corpus_id=%s", (corpus_id,)
            ).fetchone()
        return None if row is None else _corpus_from_row(row)

    def find_document_by_sha256(
        self, corpus_id: str, sha256: str
    ) -> RagDocument | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM rag_documents WHERE corpus_id=%s AND sha256=%s",
                (corpus_id, sha256),
            ).fetchone()
        return None if row is None else _document_from_row(row)

    def add_document(
        self, document: RagDocument, chunks: Sequence[RagChunk]
    ) -> None:
        try:
            self._add_document_transaction(document, chunks)
        except psycopg.errors.UniqueViolation:
            raise ValueError("duplicate document sha256") from None

    def _add_document_transaction(
        self, document: RagDocument, chunks: Sequence[RagChunk]
    ) -> None:
        with self._connection() as connection:
            corpus_row = connection.execute(
                "SELECT * FROM rag_corpora WHERE corpus_id=%s FOR UPDATE",
                (document.corpus_id,),
            ).fetchone()
            if corpus_row is None:
                raise KeyError("corpus not found")
            corpus = _corpus_from_row(corpus_row)
            if corpus.status != "draft":
                raise ValueError("published corpora are immutable")
            if (
                document.manufacturer != corpus.manufacturer
                or document.equipment_model != corpus.equipment_model
            ):
                raise ValueError("document identity does not match corpus")
            for chunk in chunks:
                if (
                    chunk.corpus_id != corpus.corpus_id
                    or chunk.document_id != document.document_id
                ):
                    raise ValueError("chunk corpus/document isolation violation")
                _validated_vector(chunk.embedding, corpus.embedding_dimensions)
            connection.execute(
                "INSERT INTO rag_documents (document_id,corpus_id,manufacturer,"
                "equipment_model,revision,language,source_url,sha256,page_count,"
                "coverage_pages) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    document.document_id,
                    document.corpus_id,
                    document.manufacturer,
                    document.equipment_model,
                    document.revision,
                    document.language,
                    document.source_url,
                    document.sha256,
                    document.page_count,
                    document.coverage_pages,
                ),
            )
            for chunk in chunks:
                connection.execute(
                    "INSERT INTO rag_chunks (chunk_id,corpus_id,document_id,ordinal,"
                    "text,page_start,page_end,section,content_hash,token_count,embedding) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)",
                    (
                        chunk.chunk_id,
                        chunk.corpus_id,
                        chunk.document_id,
                        chunk.ordinal,
                        chunk.text,
                        chunk.page_start,
                        chunk.page_end,
                        chunk.section,
                        chunk.content_hash,
                        chunk.token_count,
                        _vector_literal(chunk.embedding),
                    ),
                )

    def coverage(self, corpus_id: str) -> CorpusCoverage:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT "
                "(SELECT COUNT(*) FROM rag_documents d WHERE d.corpus_id=r.corpus_id) "
                "AS document_count,"
                "(SELECT COALESCE(SUM(d.page_count),0) FROM rag_documents d "
                "WHERE d.corpus_id=r.corpus_id) AS page_count,"
                "(SELECT COALESCE(SUM(d.coverage_pages),0) FROM rag_documents d "
                "WHERE d.corpus_id=r.corpus_id) AS coverage_pages,"
                "(SELECT COUNT(*) FROM rag_chunks c WHERE c.corpus_id=r.corpus_id) "
                "AS chunk_count FROM rag_corpora r WHERE r.corpus_id=%s",
                (corpus_id,),
            ).fetchone()
        if row is None:
            raise KeyError("corpus not found")
        return CorpusCoverage(corpus_id=corpus_id, **row)

    def preview_search(
        self,
        corpus_id: str,
        *,
        query: str,
        query_embedding: Sequence[float],
        limit: int,
    ) -> list[RagChunk]:
        corpus = self.get_corpus(corpus_id)
        if corpus is None:
            raise KeyError("corpus not found")
        _validated_vector(query_embedding, corpus.embedding_dimensions)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT chunk_id,corpus_id,document_id,ordinal,text,page_start,"
                "page_end,section,content_hash,token_count,embedding::text AS embedding "
                "FROM rag_chunks WHERE corpus_id=%s ORDER BY "
                "ts_rank_cd(search_vector,websearch_to_tsquery('simple',%s)) DESC,"
                "embedding <=> %s::vector,ordinal,chunk_id LIMIT %s",
                (corpus_id, query, _vector_literal(query_embedding), limit),
            ).fetchall()
        return [_chunk_from_row(row) for row in rows]

    def publish_corpus(
        self, asset_id: str, corpus_id: str
    ) -> ActiveCorpusChange:
        return self._activate(asset_id, corpus_id, allow_draft=True)

    def activate_published_corpus(
        self, asset_id: str, corpus_id: str
    ) -> ActiveCorpusChange:
        return self._activate(asset_id, corpus_id, allow_draft=False)

    def _activate(
        self, asset_id: str, corpus_id: str, *, allow_draft: bool
    ) -> ActiveCorpusChange:
        now = datetime.now(timezone.utc)
        with self._connection() as connection:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (asset_id,),
            )
            row = connection.execute(
                "SELECT * FROM rag_corpora WHERE corpus_id=%s FOR UPDATE",
                (corpus_id,),
            ).fetchone()
            if row is None:
                raise KeyError("corpus not found")
            corpus = _corpus_from_row(row)
            if corpus.asset_id != asset_id:
                raise ValueError("corpus asset does not match activation asset")
            if allow_draft and corpus.status != "draft":
                raise ValueError("only a draft corpus can be published")
            if not allow_draft and corpus.status != "published":
                raise ValueError("only a published corpus can be reactivated")
            if allow_draft:
                has_document = connection.execute(
                    "SELECT 1 FROM rag_documents WHERE corpus_id=%s LIMIT 1",
                    (corpus_id,),
                ).fetchone()
                if has_document is None:
                    raise ValueError("cannot publish an empty corpus")
                incompatible = connection.execute(
                    "SELECT 1 FROM rag_documents WHERE corpus_id=%s AND "
                    "(manufacturer<>%s OR equipment_model<>%s) LIMIT 1",
                    (corpus_id, corpus.manufacturer, corpus.equipment_model),
                ).fetchone()
                if incompatible is not None:
                    raise ValueError(
                        "corpus contains incompatible document identity"
                    )
                connection.execute(
                    "UPDATE rag_corpora SET status='published',"
                    "published_at=COALESCE(published_at,%s) WHERE corpus_id=%s",
                    (now, corpus_id),
                )
            active = connection.execute(
                "SELECT corpus_id FROM rag_active_corpus WHERE asset_id=%s FOR UPDATE",
                (asset_id,),
            ).fetchone()
            previous = None if active is None else active["corpus_id"]
            connection.execute(
                "INSERT INTO rag_active_corpus (asset_id,corpus_id,activated_at) "
                "VALUES (%s,%s,%s) ON CONFLICT(asset_id) DO UPDATE SET "
                "corpus_id=excluded.corpus_id,activated_at=excluded.activated_at",
                (asset_id, corpus_id, now),
            )
        return ActiveCorpusChange(asset_id, corpus_id, previous, now)

    def get_active_corpus(self, asset_id: str) -> RagCorpus | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT r.* FROM rag_active_corpus a JOIN rag_corpora r "
                "ON r.corpus_id=a.corpus_id WHERE a.asset_id=%s",
                (asset_id,),
            ).fetchone()
        return None if row is None else _corpus_from_row(row)


def _validated_vector(values: Sequence[float], dimensions: int) -> tuple[float, ...]:
    vector = tuple(float(item) for item in values)
    if len(vector) != dimensions or not all(math.isfinite(item) for item in vector):
        raise ValueError("embedding dimension does not match corpus")
    return vector


def _vector_literal(values: Sequence[float]) -> str:
    vector = tuple(float(item) for item in values)
    if not vector or not all(math.isfinite(item) for item in vector):
        raise ValueError("embedding contains invalid values")
    return "[" + ",".join(format(item, ".17g") for item in vector) + "]"


def _cosine_distance(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 1.0
    return 1.0 - numerator / (left_norm * right_norm)


def _corpus_from_row(row) -> RagCorpus:
    return RagCorpus(
        corpus_id=str(row["corpus_id"]),
        asset_id=row["asset_id"],
        manufacturer=row["manufacturer"],
        equipment_model=row["equipment_model"],
        status=row["status"],
        embedding_model=row["embedding_model"],
        embedding_dimensions=row["embedding_dimensions"],
        chunk_target_tokens=row["chunk_target_tokens"],
        chunk_overlap_tokens=row["chunk_overlap_tokens"],
        min_relevance_score=float(row["min_relevance_score"]),
        created_at=row["created_at"],
        published_at=row["published_at"],
    )


def _document_from_row(row) -> RagDocument:
    return RagDocument(
        document_id=str(row["document_id"]),
        corpus_id=str(row["corpus_id"]),
        manufacturer=row["manufacturer"],
        equipment_model=row["equipment_model"],
        revision=row["revision"],
        language=row["language"],
        source_url=row["source_url"],
        sha256=row["sha256"],
        page_count=row["page_count"],
        coverage_pages=row["coverage_pages"],
    )


def _chunk_from_row(row) -> RagChunk:
    raw_embedding = row["embedding"]
    if isinstance(raw_embedding, str):
        embedding = tuple(float(item) for item in json.loads(raw_embedding))
    else:
        embedding = tuple(raw_embedding)
    return RagChunk(
        chunk_id=str(row["chunk_id"]),
        corpus_id=str(row["corpus_id"]),
        document_id=str(row["document_id"]),
        ordinal=row["ordinal"],
        text=row["text"],
        page_start=row["page_start"],
        page_end=row["page_end"],
        section=row["section"],
        content_hash=row["content_hash"],
        token_count=row["token_count"],
        embedding=embedding,
    )
