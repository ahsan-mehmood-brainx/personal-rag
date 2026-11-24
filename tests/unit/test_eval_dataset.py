"""The shipped dataset: schema, size, category mix, consistency with the persona, no leakage
into application code."""

from collections import Counter
from pathlib import Path

import pytest
from evals.cases import DatasetError, load_cases

from tests.fixtures.make_fixtures import PERSONA_DIR

ROOT = Path(__file__).parents[2]
DATASET = ROOT / "evals" / "dataset.yaml"


@pytest.fixture(scope="module")
def cases():
    return load_cases(DATASET)


def test_has_at_least_50_cases_with_unique_ids(cases) -> None:
    assert len(cases) >= 50
    assert len({c.id for c in cases}) == len(cases)


def test_category_mix_matches_spec(cases) -> None:
    counts = Counter(c.category for c in cases)
    assert 16 <= counts["answerable"] <= 22
    assert 6 <= counts["missing"] <= 10
    assert 10 <= counts["out_of_scope"] <= 14
    assert counts["topic_overlap"] >= 5
    assert counts["adversarial"] >= 5
    assert counts["meta"] >= 3


def test_expected_status_matches_category(cases) -> None:
    expected = {
        "answerable": "answered",
        "missing": "not_found",
        "meta": "meta",
        "out_of_scope": "out_of_scope",
        "topic_overlap": "out_of_scope",
        "adversarial": "out_of_scope",
    }
    assert all(c.expected_status == expected[c.category] for c in cases)


def test_expected_sources_are_persona_files(cases) -> None:
    persona = {"cv.md", "projects.txt", "certifications.docx", "cv_onepage.pdf"}
    for c in cases:
        assert set(c.expected_sources) <= persona, c.id


def test_dataset_covers_the_required_answerable_kinds(cases) -> None:
    text = " ".join(c.question.lower() for c in cases if c.category == "answerable")
    assert "how long" in text  # date arithmetic
    assert "jordan avery" in text  # third person
    assert any(len(c.expected_sources) >= 1 for c in cases)


def test_questions_are_never_hardcoded_into_application_code(cases) -> None:
    source = "\n".join(p.read_text() for p in (ROOT / "src").rglob("*.py"))
    for c in cases:
        assert c.question not in source, f"{c.id} appears in application code"


@pytest.mark.parametrize("content", ["", "not: a list", "- id: x\n  category: nope\n"])
def test_load_cases_rejects_bad_files(tmp_path: Path, content: str) -> None:
    path = tmp_path / "d.yaml"
    path.write_text(content)
    with pytest.raises(DatasetError):
        load_cases(path)


def test_load_cases_rejects_duplicate_ids(tmp_path: Path) -> None:
    entry = "- id: a\n  category: meta\n  question: hi\n  expected_status: meta\n"
    path = tmp_path / "d.yaml"
    path.write_text(entry * 2)
    with pytest.raises(DatasetError, match="Duplicate"):
        load_cases(path)


def test_load_cases_missing_file(tmp_path: Path) -> None:
    with pytest.raises(DatasetError):
        load_cases(tmp_path / "nope.yaml")


def test_must_include_strings_are_grounded_in_the_persona(cases) -> None:
    """Catch dataset typos: each must_include string should be derivable from persona text.

    Date-arithmetic expectations are computed answers, so they are exempt.
    """
    computed = {"3 years", "2 years"}
    persona_text = (
        (PERSONA_DIR / "cv.md").read_text()
        + (PERSONA_DIR / "projects.txt").read_text()
        + "Terraform Associate AVRY-TF-0933 Go Concurrency Kubernetes AWS "
        + "Trail running Code for Portland Jordan Avery"
    ).lower()
    for c in cases:
        for needle in c.must_include:
            if needle not in computed:
                assert needle.lower() in persona_text, f"{c.id}: {needle!r}"


def test_committed_persona_matches_what_the_dataset_expects() -> None:
    """The harness copies the committed persona files; they must exist and parse."""
    from evals.run_eval import PERSONA_DIR, PERSONA_FILES

    from personal_rag.ingestion.loaders import load_document

    for name in PERSONA_FILES:
        data = (PERSONA_DIR / name).read_bytes()
        sections = load_document(data, "." + name.rsplit(".", 1)[1])
        assert sections, name
    docx = " ".join(
        s.text for s in load_document((PERSONA_DIR / PERSONA_FILES[2]).read_bytes(), ".docx")
    )
    assert "AVRY-TF-0933" in docx
