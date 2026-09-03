"""Deterministic page-aware chunking without provider-specific tokenizers."""

from hashlib import sha256
import re

from twinops.rag.models import ChunkDraft, ExtractedPage


_TOKEN = re.compile(r"\S+")
_HEADING = re.compile(r"^[A-ZÀ-ÖØ-Þ0-9][A-ZÀ-ÖØ-Þ0-9 /&().:_-]{2,80}$")
MAX_CHUNK_CHARACTERS = 16_000
MAX_CHUNKS_PER_DOCUMENT = 1_000


class ChunkingLimitError(ValueError):
    pass


def estimate_tokens(text: str) -> int:
    """Stable approximation used for versioned V1 chunk boundaries."""

    return len(_TOKEN.findall(text))


def chunk_pages(
    pages: list[ExtractedPage] | tuple[ExtractedPage, ...],
    *,
    target_tokens: int = 700,
    overlap_tokens: int = 100,
) -> tuple[ChunkDraft, ...]:
    if target_tokens <= overlap_tokens or overlap_tokens < 0:
        raise ValueError("target tokens must exceed non-negative overlap")

    sections: list[list[tuple[str, int, str | None]]] = []
    annotated: list[tuple[str, int, str | None]] = []
    current_section: str | None = None
    for page in pages:
        for line in page.text.splitlines():
            normalized = line.strip()
            if _HEADING.fullmatch(normalized):
                if current_section != normalized and annotated:
                    sections.append(annotated)
                    annotated = []
                current_section = normalized
            annotated.extend(
                (match.group(), page.page_number, current_section)
                for match in _TOKEN.finditer(normalized)
            )
    if annotated:
        sections.append(annotated)

    chunks: list[ChunkDraft] = []
    step = target_tokens - overlap_tokens
    for section_tokens in sections:
        for start in range(0, len(section_tokens), step):
            window = section_tokens[start : start + target_tokens]
            if not window:
                break
            text = " ".join(token for token, _, _ in window)
            if len(text) > MAX_CHUNK_CHARACTERS:
                raise ChunkingLimitError("chunk exceeds characters limit")
            if len(chunks) >= MAX_CHUNKS_PER_DOCUMENT:
                raise ChunkingLimitError("document exceeds maximum chunks")
            chunks.append(
                ChunkDraft(
                    ordinal=len(chunks),
                    text=text,
                    page_start=window[0][1],
                    page_end=window[-1][1],
                    section=window[0][2],
                    content_hash=sha256(text.encode("utf-8")).hexdigest(),
                    token_count=len(window),
                )
            )
            if start + target_tokens >= len(section_tokens):
                break
    return tuple(chunks)
