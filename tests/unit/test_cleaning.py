"""Cleaning: normalization, hyphen joins, bullets, whitespace, control characters."""

from personal_rag.ingestion.cleaning import clean_sections, clean_text
from personal_rag.schemas import Section


def test_joins_hyphenated_line_breaks() -> None:
    assert clean_text("software devel-\nopment") == "software development"


def test_keeps_hyphen_before_capitalized_word() -> None:
    assert "Berlin-\nBased" in clean_text("Berlin-\nBased team")


def test_nfkc_normalization() -> None:
    assert clean_text("ﬁnal ① Ｗｉｄｅ") == "final 1 Wide"


def test_collapses_spaces_and_blank_lines() -> None:
    assert clean_text("a    b\t\tc\n\n\n\n\nd") == "a b c\n\nd"


def test_strips_control_and_invisible_characters() -> None:
    assert clean_text("a\x00b\x07c\u200bd\ufeffe\u00adf") == "abcdef"


def test_normalizes_bullets() -> None:
    text = "• one\n●  two\n  ▪ three\n* four\n– five\n- six"
    assert clean_text(text) == "- one\n- two\n- three\n- four\n- five\n- six"


def test_normalizes_windows_newlines() -> None:
    assert clean_text("a\r\nb\rc") == "a\nb\nc"


def test_is_idempotent() -> None:
    once = clean_text("• Devel-\nopment  of ﬁles\n\n\n\nend")
    assert clean_text(once) == once


def test_clean_sections_drops_empty_and_cleans_headings() -> None:
    sections = [
        Section(text="  \n\n ", heading="Empty"),
        Section(text="• item", heading="Skills\u200b", page=2),
    ]
    assert clean_sections(sections) == [Section(text="- item", heading="Skills", page=2)]
