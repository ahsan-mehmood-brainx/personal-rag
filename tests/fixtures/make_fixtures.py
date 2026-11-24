"""Generate the binary persona fixtures (DOCX and PDF) for tests and evals.

Pipeline position: test support. The persona is a fictional engineer, "Jordan Avery", whose
documents are used by every unit test and by the default eval run, so real personal data is
never involved. `cv.md` and `projects.txt` are checked in as text; this script builds
`certifications.docx` (with a table) and `cv_onepage.pdf`.

Deliberate traps planted in the persona:
- Absent facts: date of birth, salary, marital status.
- Technologies that appear only as skills (Kafka, Kubernetes, Docker, React) for topic-overlap
  questions such as "Explain how Docker works".
- One fact repeated across two documents: the AWS certification (cv.md and the DOCX).
- Facts that live in only one document, so source-hit checks are meaningful: the Terraform
  certification (DOCX only) and interests and volunteering (PDF only).

Run: uv run python tests/fixtures/make_fixtures.py [output_dir]
"""

import sys
from pathlib import Path

import pymupdf
from docx import Document

PERSONA_DIR = Path(__file__).parent / "persona"

CERTIFICATIONS = [
    ("Certification", "Issuer", "Year", "Credential ID"),
    ("AWS Certified Solutions Architect Associate", "Amazon Web Services", "2021", "AVRY-AWS-2210"),
    ("HashiCorp Certified: Terraform Associate", "HashiCorp", "2022", "AVRY-TF-0933"),
    (
        "Certified Kubernetes Application Developer",
        "Cloud Native Computing Foundation",
        "2023",
        "AVRY-CKAD-5518",
    ),
]

PDF_LINES = [
    ("Jordan Avery", 18),
    ("Senior Software Engineer | Portland, Oregon | jordan.avery@example.com", 10),
    ("", 10),
    ("SUMMARY", 12),
    ("Software engineer focused on data pipelines, backend services and developer tooling.", 10),
    ("", 10),
    ("EXPERIENCE", 12),
    ("Helios Cloud, Senior Software Engineer, September 2022 to present", 10),
    ("Northwind Analytics, Software Engineer, July 2019 to August 2022", 10),
    ("Brightwave Systems, Junior Software Engineer, March 2017 to June 2019", 10),
    ("", 10),
    ("EDUCATION", 12),
    ("Lakeview University, BSc Computer Science, 2012 to 2016", 10),
    ("", 10),
    ("VOLUNTEERING", 12),
    ("Mentor at Code for Portland since 2020, helping career changers learn Python.", 10),
    ("", 10),
    ("INTERESTS", 12),
    ("Trail running, bouldering and designing board games.", 10),
]


def make_docx(path: Path) -> None:
    """Certifications document: headings, a paragraph and a table."""
    doc = Document()
    doc.add_heading("Jordan Avery: Certifications and Training", level=0)
    doc.add_heading("Certifications", level=1)
    doc.add_paragraph(
        "Professional certifications held by Jordan Avery, with credential identifiers."
    )
    table = doc.add_table(rows=len(CERTIFICATIONS), cols=4)
    table.style = "Table Grid"
    for row_index, row in enumerate(CERTIFICATIONS):
        for col_index, value in enumerate(row):
            table.cell(row_index, col_index).text = value
    doc.add_heading("Training", level=1)
    doc.add_paragraph(
        "Completed the Advanced Go Concurrency workshop in 2020 and an internal incident "
        "response course at Northwind Analytics in 2021."
    )
    doc.save(str(path))


def make_pdf(path: Path) -> None:
    """One-page CV summary with text on a real text layer."""
    doc = pymupdf.open()
    page = doc.new_page()
    y = 60.0
    for text, size in PDF_LINES:
        if text:
            page.insert_text((60, y), text, fontsize=size)
        y += size + 8
    doc.save(str(path))
    doc.close()


def make_scanned_pdf(path: Path) -> None:
    """A PDF page with no text layer (just a drawn rectangle), to test scanned detection."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.draw_rect(pymupdf.Rect(50, 50, 300, 300), fill=(0.8, 0.8, 0.8))
    doc.save(str(path))
    doc.close()


def make_all(directory: Path = PERSONA_DIR) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    make_docx(directory / "certifications.docx")
    make_pdf(directory / "cv_onepage.pdf")


if __name__ == "__main__":
    make_all(Path(sys.argv[1]) if len(sys.argv) > 1 else PERSONA_DIR)
    print("Generated certifications.docx and cv_onepage.pdf")
