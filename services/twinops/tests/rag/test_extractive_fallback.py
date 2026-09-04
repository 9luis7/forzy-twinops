from datetime import datetime, timezone

import pytest

from twinops.rag.chunking import chunk_pages
from twinops.rag.extractive import select_safe_excerpts
from twinops.rag.models import (
    ExtractedPage,
    RagChunk,
    RagCorpus,
    RagDocument,
    RetrievalCandidate,
)
from twinops.rag.retrieval import FusedRetrievalHit


NOW = datetime(2026, 9, 4, tzinfo=timezone.utc)


def _hit(chunk_id: str, text: str, *, rank: int, language: str = "pt,en"):
    corpus = RagCorpus.draft(
        corpus_id="corpus-1",
        asset_id="forzy-motor-01",
        manufacturer="WEG",
        equipment_model="W22",
        embedding_model="gemini-embedding-2",
        embedding_dimensions=3,
        min_relevance_score=0.2,
        created_at=NOW,
    ).published(NOW)
    document = RagDocument(
        document_id=f"document-{chunk_id}",
        corpus_id=corpus.corpus_id,
        manufacturer="WEG",
        equipment_model="W22",
        revision="2026-01",
        language=language,
        source_url="https://manufacturer.example/manual.pdf",
        sha256="a" * 64,
        page_count=10,
        coverage_pages=10,
    )
    chunk = RagChunk(
        chunk_id=chunk_id,
        corpus_id=corpus.corpus_id,
        document_id=document.document_id,
        ordinal=rank - 1,
        text=text,
        page_start=rank,
        page_end=rank,
        section="MAINTENANCE",
        content_hash=(f"{rank:x}" * 64)[:64],
        token_count=max(1, len(text.split())),
        embedding=(1.0, 0.0, 0.0),
    )
    candidate = RetrievalCandidate(chunk, document, 1.0 / rank)
    return FusedRetrievalHit(candidate, 1.0 / rank, rank, rank)


def test_prefers_exact_relevant_prose_and_rejects_numeric_table_prefix():
    table = (
        "80 2 132 2 225 2 9000 355 2 6000 4 4 4 20000 6 6 6 8 8\n"
    )
    sentence = (
        "Para cada incremento de 15 °C acima da temperatura do mancal, "
        "o intervalo de relubrificação deve ser reduzido pela metade."
    )
    hit = _hit("chunk-1", table + sentence, rank=1)

    selected = select_safe_excerpts(
        "Quando o intervalo de relubrificação deve ser reduzido?", (hit,)
    )

    assert [item.excerpt for item in selected] == [sentence]
    assert selected[0].excerpt in hit.candidate.chunk.text
    assert hit.candidate.chunk.text[selected[0].start:selected[0].end] == sentence
    assert selected[0].hit.candidate.chunk.content_hash == "1" * 64


@pytest.mark.parametrize(
    "table_text",
    [
        "Bearing type | grease quantity | interval hours",
        "Bearing type\tgrease quantity\tinterval hours",
        "Bearing type    grease quantity    interval hours",
        "Bearing type\u00a0\u00a0grease quantity\u00a0\u00a0interval hours",
    ],
)
def test_rejects_textual_table_structure_without_numeric_cells(table_text):
    hit = _hit("chunk-1", table_text, rank=1, language="en")

    selected = select_safe_excerpts(
        "What bearing interval information is listed?", (hit,)
    )

    assert selected == ()


def test_keeps_relevant_prose_with_one_ocr_spacing_gap():
    sentence = (
        "Inspect  bearing lubrication before starting the electric motor."
    )
    hit = _hit("chunk-1", sentence, rank=1, language="en")

    selected = select_safe_excerpts(
        "How should bearing lubrication be inspected?", (hit,)
    )

    assert [item.excerpt for item in selected] == [sentence]


def test_rejects_textual_table_after_real_chunking_normalizes_columns():
    chunks = chunk_pages(
        [
            ExtractedPage(
                page_number=1,
                text=(
                    "Bearing type\tGrease quantity\tInterval hours\n"
                    "Ball bearing\tStandard grease\tRoutine interval"
                ),
            )
        ],
        target_tokens=50,
        overlap_tokens=0,
    )
    hit = _hit("chunk-1", chunks[0].text, rank=1, language="en")

    selected = select_safe_excerpts(
        "What bearing interval information is listed?", (hit,)
    )

    assert selected == ()


def test_uses_one_question_compatible_language_when_available():
    english = _hit(
        "chunk-1",
        "Inspect bearing lubrication before starting the electric motor.",
        rank=1,
        language="en",
    )
    portuguese = _hit(
        "chunk-2",
        "Verifique a lubrificação do rolamento antes de partir o motor elétrico.",
        rank=2,
        language="pt",
    )

    selected = select_safe_excerpts(
        "Como verificar a lubrificação do rolamento?", (english, portuguese)
    )

    assert [item.excerpt for item in selected] == [
        "Verifique a lubrificação do rolamento antes de partir o motor elétrico."
    ]
    assert {item.language for item in selected} == {"pt"}


def test_cross_language_aliases_select_one_safe_source_language_without_translation():
    english = _hit(
        "chunk-1",
        "Inspect bearing lubrication before starting the electric motor.",
        rank=1,
        language="en",
    )

    selected = select_safe_excerpts(
        "Como verificar a lubrificação do rolamento?", (english,)
    )

    assert [item.excerpt for item in selected] == [
        "Inspect bearing lubrication before starting the electric motor."
    ]
    assert selected[0].language == "en"


def test_multilingual_unknown_language_keeps_only_highest_ranked_span():
    english = _hit(
        "chunk-1",
        "Bearing inspection prevents failures.",
        rank=1,
        language="pt,en",
    )
    portuguese = _hit(
        "chunk-2",
        "Inspecao rolamento evita falhas.",
        rank=2,
        language="pt,en",
    )

    selected = select_safe_excerpts(
        "Como verificar o rolamento?", (english, portuguese)
    )

    assert len(selected) == 1
    assert selected[0].language == "und"
    chunk_text = selected[0].hit.candidate.chunk.text
    assert chunk_text[selected[0].start:selected[0].end] == selected[0].excerpt


def test_removes_exact_and_high_overlap_repetition_across_hits():
    first = _hit(
        "chunk-1",
        "Inspect bearing lubrication before starting the electric motor.",
        rank=1,
        language="en",
    )
    duplicate = _hit(
        "chunk-2",
        "Inspect bearing lubrication before starting the electric motor.",
        rank=2,
        language="en",
    )
    near_duplicate = _hit(
        "chunk-3",
        "Inspect the bearing lubrication before starting the electric motor.",
        rank=3,
        language="en",
    )

    selected = select_safe_excerpts("How should bearing lubrication be inspected?", (
        first,
        duplicate,
        near_duplicate,
    ))

    assert len(selected) == 1
    assert selected[0].hit.candidate.chunk.chunk_id == "chunk-1"


def test_selects_at_most_one_excerpt_from_the_same_chunk():
    hit = _hit(
        "chunk-1",
        (
            "Inspect bearing lubrication before starting the electric motor. "
            "Verify bearing lubrication after the electric motor stops."
        ),
        rank=1,
        language="en",
    )

    selected = select_safe_excerpts(
        "How should bearing lubrication be inspected and verified?", (hit,)
    )

    assert len(selected) == 1
    assert selected[0].excerpt == (
        "Inspect bearing lubrication before starting the electric motor."
    )


def test_returns_no_excerpt_when_only_unsafe_or_irrelevant_spans_exist():
    numeric = _hit(
        "chunk-1",
        "6220 24 7324 72 1700 1200 6319 45 4500 3500 3300 2500",
        rank=1,
    )
    irrelevant = _hit(
        "chunk-2",
        "The nameplate contains identification details for the electric motor.",
        rank=2,
        language="en",
    )

    selected = select_safe_excerpts(
        "Como verificar a umidade nos rolamentos?", (numeric, irrelevant)
    )

    assert selected == ()


def test_never_cuts_a_long_sentence_to_fit_the_excerpt_limit():
    long_sentence = "Lubrication " + "carefully " * 70 + "before startup."
    safe_sentence = "Inspect lubrication before startup."
    hit = _hit(
        "chunk-1",
        f"{long_sentence} {safe_sentence}",
        rank=1,
        language="en",
    )

    selected = select_safe_excerpts("How should lubrication be inspected?", (hit,))

    assert [item.excerpt for item in selected] == [safe_sentence]
    assert all(len(item.excerpt) <= 500 for item in selected)
