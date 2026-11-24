"""Loaders: headings, hierarchy, PDF pages, DOCX tables in order, scanned-PDF detection."""

from pathlib import Path

import pymupdf
import pytest
from docx import Document

from personal_rag.ingestion.loaders import (
    DocumentParseError,
    ScannedPdfError,
    load_document,
    load_docx,
    load_pdf,
    load_text,
)
from tests.fixtures.make_fixtures import make_scanned_pdf


def test_markdown_headings_form_a_hierarchy() -> None:
    md = b"# Me\nintro\n## Work\n### Acme\nbuilt things\n### Beta\nmore\n## Education\nschool\n"
    sections = load_text(md, markdown=True)
    assert [s.heading for s in sections] == [
        "Me",
        "Me > Work > Acme",
        "Me > Work > Beta",
        "Me > Education",
    ]
    assert sections[1].text == "built things"


def test_markdown_ignores_hash_lines_inside_code_fences() -> None:
    md = b"# Title\n```\n# not a heading\n```\nbody\n"
    sections = load_text(md, markdown=True)
    assert len(sections) == 1
    assert "# not a heading" in sections[0].text


def test_text_before_first_heading_has_no_heading() -> None:
    sections = load_text(b"preamble\n\n# H\nbody", markdown=True)
    assert sections[0].heading is None
    assert sections[1].heading == "H"


def test_plain_text_headings_caps_and_colon() -> None:
    txt = b"WORK HISTORY\nAcme, 2020.\n\nSkills:\nPython and Go.\n\nnormal sentence here.\n"
    sections = load_text(txt, markdown=False)
    assert [s.heading for s in sections] == ["WORK HISTORY", "Skills"]
    assert "normal sentence here." in sections[1].text


def test_plain_text_heading_heuristic_limits() -> None:
    # Too long, list items, and lines glued to the previous line are not headings.
    long_caps = "A" * 70
    txt = f"{long_caps}\n\n- ITEM\n\nline one\nSTACK: PYTHON\n".encode()
    sections = load_text(txt, markdown=False)
    assert len(sections) == 1
    assert sections[0].heading is None


def test_persona_text_files(persona_dir: Path) -> None:
    sections = load_document((persona_dir / "projects.txt").read_bytes(), ".txt")
    headings = [s.heading for s in sections]
    assert "ORDER TRACKER SERVICE" in headings
    assert "DEMAND FORECASTING PIPELINE" in headings


def test_pdf_pages_are_one_based(tmp_path: Path) -> None:
    doc = pymupdf.open()
    for number in (1, 2):
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 550, 700), f"Page {number} " + "words " * 60)
    sections = load_pdf(doc.tobytes())
    assert [s.page for s in sections] == [1, 2]
    assert sections[1].text.startswith("Page 2")


def test_persona_pdf(persona_dir: Path) -> None:
    sections = load_pdf((persona_dir / "cv_onepage.pdf").read_bytes())
    assert len(sections) == 1
    assert "Northwind Analytics" in sections[0].text
    assert sections[0].page == 1


def test_scanned_pdf_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    make_scanned_pdf(path)
    with pytest.raises(ScannedPdfError, match="OCR"):
        load_pdf(path.read_bytes())


def test_corrupt_pdf_raises_parse_error() -> None:
    with pytest.raises(DocumentParseError):
        load_pdf(b"%PDF-1.4 this is not really a pdf")


def test_docx_headings_and_hierarchy(tmp_path: Path) -> None:
    doc = Document()
    doc.add_heading("Title Line", level=0)
    doc.add_paragraph("under title")
    doc.add_heading("Section A", level=1)
    doc.add_paragraph("body a")
    doc.add_heading("Sub", level=2)
    doc.add_paragraph("body sub")
    path = tmp_path / "t.docx"
    doc.save(str(path))
    sections = load_docx(path.read_bytes())
    assert [s.heading for s in sections] == [
        "Title Line",
        "Title Line > Section A",
        "Title Line > Section A > Sub",
    ]


def test_docx_table_in_document_order(tmp_path: Path) -> None:
    doc = Document()
    doc.add_heading("Certs", level=1)
    doc.add_paragraph("before table")
    table = doc.add_table(rows=2, cols=3)
    for r, row in enumerate([("A", "B", "C"), ("1", "2", "3")]):
        for c, value in enumerate(row):
            table.cell(r, c).text = value
    doc.add_paragraph("after table")
    path = tmp_path / "t.docx"
    doc.save(str(path))
    (section,) = load_docx(path.read_bytes())
    assert section.text.split("\n") == ["before table", "A | B | C", "1 | 2 | 3", "after table"]


def test_docx_merged_cells_are_not_duplicated(tmp_path: Path) -> None:
    doc = Document()
    table = doc.add_table(rows=1, cols=3)
    merged = table.cell(0, 0).merge(table.cell(0, 1))
    merged.text = "Wide"
    table.cell(0, 2).text = "Narrow"
    path = tmp_path / "t.docx"
    doc.save(str(path))
    (section,) = load_docx(path.read_bytes())
    assert section.text == "Wide | Narrow"


def test_persona_docx_contains_table_rows(persona_dir: Path) -> None:
    sections = load_docx((persona_dir / "certifications.docx").read_bytes())
    combined = "\n".join(s.text for s in sections)
    assert "HashiCorp Certified: Terraform Associate | HashiCorp | 2022 | AVRY-TF-0933" in combined


def test_corrupt_docx_raises_parse_error() -> None:
    with pytest.raises(DocumentParseError):
        load_docx(b"PK\x03\x04 nope")
