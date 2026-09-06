CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_corpora (
    corpus_id UUID PRIMARY KEY,
    asset_id TEXT NOT NULL CONSTRAINT rag_corpora_asset_check
        CHECK (asset_id = 'forzy-motor-01'),
    manufacturer TEXT NOT NULL CHECK (BTRIM(manufacturer) <> ''),
    equipment_model TEXT NOT NULL CHECK (BTRIM(equipment_model) <> ''),
    status TEXT NOT NULL CONSTRAINT rag_corpora_status_check
        CHECK (status IN ('draft', 'published')),
    embedding_model TEXT NOT NULL CHECK (BTRIM(embedding_model) <> ''),
    embedding_dimensions INTEGER NOT NULL CONSTRAINT rag_corpora_dimensions_check
        CHECK (embedding_dimensions > 0),
    chunk_target_tokens INTEGER NOT NULL CONSTRAINT rag_corpora_chunk_target_check
        CHECK (chunk_target_tokens > 0),
    chunk_overlap_tokens INTEGER NOT NULL CONSTRAINT rag_corpora_chunk_overlap_check CHECK (
        chunk_overlap_tokens >= 0 AND chunk_overlap_tokens < chunk_target_tokens
    ),
    min_relevance_score DOUBLE PRECISION NOT NULL DEFAULT 0
        CONSTRAINT rag_corpora_relevance_check CHECK (
        min_relevance_score >= 0 AND min_relevance_score <= 1
    ),
    created_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ,
    CONSTRAINT rag_corpora_publication_check CHECK (
        (status = 'draft' AND published_at IS NULL)
        OR (status = 'published' AND published_at IS NOT NULL)
    ),
    CONSTRAINT rag_corpora_manual_identity_key
        UNIQUE (corpus_id, manufacturer, equipment_model),
    CONSTRAINT rag_corpora_asset_identity_key UNIQUE (corpus_id, asset_id)
);

CREATE TABLE IF NOT EXISTS rag_documents (
    document_id UUID PRIMARY KEY,
    corpus_id UUID NOT NULL,
    manufacturer TEXT NOT NULL CHECK (manufacturer <> ''),
    equipment_model TEXT NOT NULL CHECK (equipment_model <> ''),
    revision TEXT NOT NULL CHECK (revision <> ''),
    language TEXT NOT NULL CHECK (language <> ''),
    source_url TEXT NOT NULL CHECK (source_url LIKE 'https://%'),
    sha256 CHAR(64) NOT NULL CONSTRAINT rag_documents_sha_check
        CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    page_count INTEGER NOT NULL CONSTRAINT rag_documents_pages_check
        CHECK (page_count >= 1 AND page_count <= 400),
    coverage_pages INTEGER NOT NULL CONSTRAINT rag_documents_coverage_check CHECK (
        coverage_pages >= 1 AND coverage_pages <= page_count
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT rag_documents_manual_identity_fkey
        FOREIGN KEY (corpus_id, manufacturer, equipment_model)
        REFERENCES rag_corpora(corpus_id, manufacturer, equipment_model),
    CONSTRAINT rag_documents_identity_key UNIQUE (document_id, corpus_id),
    CONSTRAINT rag_documents_corpus_sha_key UNIQUE (corpus_id, sha256)
);

CREATE TABLE IF NOT EXISTS rag_chunks (
    chunk_id UUID PRIMARY KEY,
    corpus_id UUID NOT NULL CONSTRAINT rag_chunks_corpus_fkey
        REFERENCES rag_corpora(corpus_id),
    document_id UUID NOT NULL,
    ordinal INTEGER NOT NULL CONSTRAINT rag_chunks_ordinal_check CHECK (ordinal >= 0),
    text TEXT NOT NULL CONSTRAINT rag_chunks_text_check CHECK (text <> ''),
    page_start INTEGER NOT NULL CONSTRAINT rag_chunks_page_start_check
        CHECK (page_start >= 1),
    page_end INTEGER NOT NULL CONSTRAINT rag_chunks_page_range_check
        CHECK (page_end >= page_start),
    section TEXT,
    content_hash CHAR(64) NOT NULL CONSTRAINT rag_chunks_hash_check
        CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    token_count INTEGER NOT NULL CONSTRAINT rag_chunks_token_count_check
        CHECK (token_count > 0),
    search_vector TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('simple', text)
    ) STORED,
    embedding VECTOR NOT NULL,
    CONSTRAINT rag_chunks_document_fkey FOREIGN KEY (document_id, corpus_id)
        REFERENCES rag_documents(document_id, corpus_id),
    CONSTRAINT rag_chunks_ordinal_key UNIQUE (corpus_id, document_id, ordinal)
);

CREATE INDEX IF NOT EXISTS rag_chunks_corpus_idx
    ON rag_chunks (corpus_id, ordinal);
CREATE INDEX IF NOT EXISTS rag_chunks_search_vector_idx
    ON rag_chunks USING GIN (search_vector);

CREATE TABLE IF NOT EXISTS rag_active_corpus (
    asset_id TEXT PRIMARY KEY,
    corpus_id UUID NOT NULL,
    activated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT rag_active_corpus_pointer_fkey FOREIGN KEY (corpus_id, asset_id)
        REFERENCES rag_corpora(corpus_id, asset_id)
);

-- Deliberately no HNSW/IVFFlat index in V1. Publication and rollback are
-- performed by one transaction that locks the selected corpus and upserts the
-- single rag_active_corpus pointer for the asset.
