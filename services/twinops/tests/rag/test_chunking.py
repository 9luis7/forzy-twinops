import pytest

from twinops.rag.chunking import (
    MAX_CHUNK_CHARACTERS,
    MAX_CHUNKS_PER_DOCUMENT,
    ChunkingLimitError,
    chunk_pages,
    estimate_tokens,
)
from twinops.rag.models import ExtractedPage


def test_chunking_targets_700_tokens_with_100_token_overlap():
    text = "\n".join(
        ["MAINTENANCE"] + [f"word{index}" for index in range(1_500)]
    )

    chunks = chunk_pages(
        [ExtractedPage(page_number=7, text=text)],
        target_tokens=700,
        overlap_tokens=100,
    )

    assert len(chunks) == 3
    assert max(estimate_tokens(chunk.text) for chunk in chunks) <= 700
    first = chunks[0].text.split()
    second = chunks[1].text.split()
    assert first[-100:] == second[:100]
    assert all(chunk.page_start == 7 and chunk.page_end == 7 for chunk in chunks)
    assert chunks[0].section == "MAINTENANCE"
    assert all(len(chunk.content_hash) == 64 for chunk in chunks)
    assert len({chunk.content_hash for chunk in chunks}) == len(chunks)


def test_chunking_preserves_cross_page_coverage():
    chunks = chunk_pages(
        [
            ExtractedPage(page_number=2, text="SECTION ONE\n" + "a " * 500),
            ExtractedPage(page_number=3, text="b " * 500),
        ],
        target_tokens=700,
        overlap_tokens=100,
    )

    assert chunks[0].page_start == 2
    assert chunks[0].page_end == 3
    assert chunks[-1].page_end == 3


def test_chunking_never_crosses_section_boundaries_or_overlaps_into_next_section():
    chunks = chunk_pages(
        [
            ExtractedPage(
                page_number=1,
                text=(
                    "SECTION ONE\n"
                    + "alpha " * 650
                    + "\nSECTION TWO\n"
                    + "beta " * 650
                ),
            )
        ],
        target_tokens=700,
        overlap_tokens=100,
    )

    assert [chunk.section for chunk in chunks] == ["SECTION ONE", "SECTION TWO"]
    assert "beta" not in chunks[0].text.split()
    assert "alpha" not in chunks[1].text.split()


def test_chunking_rejects_one_oversized_token_without_whitespace():
    with pytest.raises(ChunkingLimitError, match="characters"):
        chunk_pages(
            [
                ExtractedPage(
                    page_number=1,
                    text="x" * (MAX_CHUNK_CHARACTERS + 1),
                )
            ]
        )


def test_chunking_caps_total_gateway_work():
    pages = [
        ExtractedPage(page_number=index + 1, text=f"SECTION {index}\nword")
        for index in range(MAX_CHUNKS_PER_DOCUMENT + 1)
    ]

    with pytest.raises(ChunkingLimitError, match="chunks"):
        chunk_pages(pages)
