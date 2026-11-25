"""Chunking: size limits, overlap, section boundaries, small-section merge, metadata."""

import pytest

from personal_rag.ingestion.chunking import (
    MIN_SECTION_TOKENS,
    chunk_document,
    count_tokens,
    merge_small_sections,
)
from personal_rag.schemas import Section

KWARGS = {
    "doc_id": "abc123",
    "filename": "cv.md",
    "embedding_model": "test-model",
    "ingested_at": "2026-01-01T00:00:00+00:00",
}


def chunks_for(sections: list[Section], size: int = 100, overlap: int = 20):
    return chunk_document(sections=sections, chunk_size=size, overlap=overlap, **KWARGS)


def sentence_block(n: int, prefix: str = "S") -> str:
    return " ".join(
        f"{prefix}{i} is a fairly ordinary sentence about work and tools." for i in range(n)
    )


def test_chunks_respect_size_limit() -> None:
    chunks = chunks_for([Section(text=sentence_block(60), heading="Big")], size=100)
    assert len(chunks) > 1
    assert all(c.token_count <= 100 for c in chunks)
    assert all(c.token_count == count_tokens(c.text) for c in chunks)


def test_consecutive_chunks_overlap_on_whole_sentences() -> None:
    chunks = chunks_for([Section(text=sentence_block(60), heading="Big")], size=100, overlap=30)
    for earlier, later in zip(chunks, chunks[1:], strict=False):
        last_sentence = earlier.text.split(". ")[-1].strip()
        assert last_sentence in later.text, "overlap should repeat trailing material"


def test_zero_overlap_means_no_repeated_text() -> None:
    chunks = chunks_for([Section(text=sentence_block(60), heading="Big")], size=100, overlap=0)
    seen = " ".join(c.text for c in chunks)
    assert seen.count("S10 is") == 1


def test_never_splits_across_sections() -> None:
    sections = [
        Section(text=sentence_block(10, "A"), heading="First"),
        Section(text=sentence_block(10, "B"), heading="Second"),
    ]
    for chunk in chunks_for(sections, size=300):
        assert not ("A1 " in chunk.text and "B1 " in chunk.text)
    headings = {c.section for c in chunks_for(sections, size=300)}
    assert headings == {"First", "Second"}


def test_small_sections_merge_forward_keeping_both_headings() -> None:
    tiny = Section(text="Python, Go", heading="Skills")
    big = Section(text=sentence_block(10), heading="Experience")
    merged = merge_small_sections([tiny, big])
    assert len(merged) == 1
    assert merged[0].heading == "Skills / Experience"
    assert merged[0].text.startswith("Python, Go")
    assert count_tokens(tiny.text) < MIN_SECTION_TOKENS


def test_merge_does_not_repeat_parent_heading() -> None:
    parent = Section(text="Intro line", heading="Jordan")
    child = Section(text=sentence_block(10), heading="Jordan > Summary")
    assert merge_small_sections([parent, child])[0].heading == "Jordan > Summary"


def test_small_last_section_stays_alone() -> None:
    merged = merge_small_sections(
        [Section(text=sentence_block(10), heading="A"), Section(text="tiny", heading="B")]
    )
    assert [s.heading for s in merged] == ["A", "B"]


def test_chain_of_small_sections_merges_until_big_enough() -> None:
    sections = [
        Section(text="a", heading="X"),
        Section(text="b", heading="Y"),
        Section(text=sentence_block(10), heading="Z"),
    ]
    merged = merge_small_sections(sections)
    assert len(merged) == 1
    assert merged[0].heading == "X / Y / Z"


def test_long_paragraph_falls_back_to_lines_then_sentences() -> None:
    bullets = "\n".join(f"- bullet number {i} describing some work in detail" for i in range(40))
    chunks = chunks_for([Section(text=bullets, heading="Bullets")], size=80, overlap=0)
    assert len(chunks) > 1
    # Splitting on lines means no bullet is cut in half.
    for chunk in chunks:
        assert all(line.startswith("- bullet number") for line in chunk.text.split("\n"))


def test_unbroken_text_is_hard_split_within_limit() -> None:
    chunks = chunks_for([Section(text="x" * 4000, heading="Blob")], size=100, overlap=0)
    assert len(chunks) > 1
    assert all(c.token_count <= 100 for c in chunks)


def test_embed_text_has_contextual_header_and_text_is_raw() -> None:
    (chunk,) = chunks_for([Section(text=sentence_block(10), heading="Experience")], size=400)
    assert chunk.embed_text == f"Document: cv.md | Section: Experience\n\n{chunk.text}"
    assert not chunk.text.startswith("Document:")


def test_missing_heading_becomes_general() -> None:
    (chunk,) = chunks_for([Section(text=sentence_block(10))], size=400)
    assert chunk.section == "General"
    assert chunk.embed_text.startswith("Document: cv.md | Section: General\n\n")


def test_metadata_fields() -> None:
    sections = [
        Section(text=sentence_block(10), heading="A", page=3),
        Section(text=sentence_block(10), heading="B"),
    ]
    chunks = chunks_for(sections, size=400)
    assert [c.chunk_id for c in chunks] == ["abc123:0", "abc123:1"]
    assert [c.chunk_index for c in chunks] == [0, 1]
    assert chunks[0].page == 3
    assert chunks[1].page is None
    assert all(c.doc_id == "abc123" and c.filename == "cv.md" for c in chunks)
    assert all(c.embedding_model == "test-model" for c in chunks)
    assert all(c.ingested_at == KWARGS["ingested_at"] for c in chunks)


def test_empty_input_gives_no_chunks() -> None:
    assert chunks_for([]) == []


@pytest.mark.parametrize("size", [60, 120, 400])
def test_all_text_is_preserved_across_chunks(size: int) -> None:
    text = sentence_block(40)
    chunks = chunks_for([Section(text=text, heading="H")], size=size, overlap=10)
    joined = " ".join(c.text for c in chunks)
    for i in range(40):
        assert f"S{i} is" in joined


def test_merge_keeps_both_headings_for_siblings_with_shared_prefix() -> None:
    first = Section(text="tiny", heading="Skills")
    second = Section(text=sentence_block(10), heading="Skills Summary")
    assert merge_small_sections([first, second])[0].heading == "Skills / Skills Summary"
