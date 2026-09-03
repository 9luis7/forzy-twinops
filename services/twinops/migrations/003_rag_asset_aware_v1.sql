CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_corpora (
    corpus_id UUID PRIMARY KEY,
    asset_id TEXT NOT NULL CHECK (asset_id = 'forzy-motor-01'),
    manufacturer TEXT NOT NULL CHECK (BTRIM(manufacturer) <> ''),
    equipment_model TEXT NOT NULL CHECK (BTRIM(equipment_model) <> ''),
    status TEXT NOT NULL CHECK (status IN ('draft', 'published')),
    embedding_model TEXT NOT NULL CHECK (BTRIM(embedding_model) <> ''),
    embedding_dimensions INTEGER NOT NULL CHECK (embedding_dimensions > 0),
    chunk_target_tokens INTEGER NOT NULL CHECK (chunk_target_tokens > 0),
    chunk_overlap_tokens INTEGER NOT NULL CHECK (
        chunk_overlap_tokens >= 0 AND chunk_overlap_tokens < chunk_target_tokens
    ),
    min_relevance_score DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (
        min_relevance_score >= 0 AND min_relevance_score <= 1
    ),
    created_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ,
    CHECK (
        (status = 'draft' AND published_at IS NULL)
        OR (status = 'published' AND published_at IS NOT NULL)
    ),
    UNIQUE (corpus_id, manufacturer, equipment_model),
    UNIQUE (corpus_id, asset_id)
);

CREATE TABLE IF NOT EXISTS rag_documents (
    document_id UUID PRIMARY KEY,
    corpus_id UUID NOT NULL,
    manufacturer TEXT NOT NULL CHECK (manufacturer <> ''),
    equipment_model TEXT NOT NULL CHECK (equipment_model <> ''),
    revision TEXT NOT NULL CHECK (revision <> ''),
    language TEXT NOT NULL CHECK (language <> ''),
    source_url TEXT NOT NULL CHECK (source_url LIKE 'https://%'),
    sha256 CHAR(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    page_count INTEGER NOT NULL CHECK (page_count BETWEEN 1 AND 400),
    coverage_pages INTEGER NOT NULL CHECK (
        coverage_pages BETWEEN 1 AND page_count
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (corpus_id, manufacturer, equipment_model)
        REFERENCES rag_corpora(corpus_id, manufacturer, equipment_model),
    UNIQUE (document_id, corpus_id),
    UNIQUE (corpus_id, sha256)
);

CREATE TABLE IF NOT EXISTS rag_chunks (
    chunk_id UUID PRIMARY KEY,
    corpus_id UUID NOT NULL REFERENCES rag_corpora(corpus_id),
    document_id UUID NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    text TEXT NOT NULL CHECK (text <> ''),
    page_start INTEGER NOT NULL CHECK (page_start >= 1),
    page_end INTEGER NOT NULL CHECK (page_end >= page_start),
    section TEXT,
    content_hash CHAR(64) NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    token_count INTEGER NOT NULL CHECK (token_count > 0),
    search_vector TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('simple', text)
    ) STORED,
    embedding VECTOR NOT NULL,
    FOREIGN KEY (document_id, corpus_id)
        REFERENCES rag_documents(document_id, corpus_id),
    UNIQUE (corpus_id, document_id, ordinal)
);

CREATE INDEX IF NOT EXISTS rag_chunks_corpus_idx
    ON rag_chunks (corpus_id, ordinal);
CREATE INDEX IF NOT EXISTS rag_chunks_search_vector_idx
    ON rag_chunks USING GIN (search_vector);

CREATE TABLE IF NOT EXISTS rag_active_corpus (
    asset_id TEXT PRIMARY KEY,
    corpus_id UUID NOT NULL,
    activated_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (corpus_id, asset_id)
        REFERENCES rag_corpora(corpus_id, asset_id)
);

-- Deliberately no HNSW/IVFFlat index in V1. Publication and rollback are
-- performed by one transaction that locks the selected corpus and upserts the
-- single rag_active_corpus pointer for the asset.
