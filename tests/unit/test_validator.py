"""Gate 3: citation validation and downgrade logic."""

import logging

import pytest

from personal_rag.query.validator import validate_answer
from personal_rag.schemas import GroundedAnswer

PROVIDED = {"S1", "S2", "S3"}


def answer(status: str = "answered", text: str = "You worked at X.", cites=("S1",)):
    return GroundedAnswer(status=status, answer=text, citations=list(cites))  # type: ignore[arg-type]


def test_valid_answer_passes_with_citations_in_order() -> None:
    result = validate_answer(answer(cites=("S3", "S1")), PROVIDED)
    assert result.status == "answered"
    assert result.labels == ["S3", "S1"]
    assert result.text == "You worked at X."


def test_invalid_labels_are_dropped() -> None:
    result = validate_answer(answer(cites=("S1", "S9", "bogus")), PROVIDED)
    assert result.status == "answered"
    assert result.labels == ["S1"]


def test_answered_with_only_invalid_citations_is_downgraded_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        result = validate_answer(answer(cites=("S7",)), PROVIDED)
    assert result.status == "not_found"
    assert result.text == ""
    assert "downgraded" in caplog.text


def test_answered_with_no_citations_is_downgraded() -> None:
    assert validate_answer(answer(cites=()), PROVIDED).status == "not_found"


def test_model_not_found_discards_model_text() -> None:
    said = answer(status="not_found", text="Maybe in 2020?", cites=("S1",))
    result = validate_answer(said, PROVIDED)
    assert result.status == "not_found"
    assert result.text == ""
    assert result.labels == []


def test_label_formatting_variants_are_normalized_and_deduplicated() -> None:
    result = validate_answer(answer(cites=("[S1]", " s1 ", "S2")), PROVIDED)
    assert result.labels == ["S1", "S2"]


def test_blank_answer_text_is_downgraded() -> None:
    assert validate_answer(answer(text="   "), PROVIDED).status == "not_found"
