"""Loaders: turn PDF, DOCX, TXT and MD bytes into a list of `Section` objects.

Pipeline position: right after validation. A loader's only job is to recover structure
(headings, pages, tables) from the file; it does not clean text or decide chunk sizes.

Heading handling: DOCX and Markdown headings are hierarchical, so a section's heading is the
path of its ancestors, for example "Jordan Avery > Experience > Northwind Analytics". The path
keeps context that a bare "Northwind Analytics" would lose once embedded.
"""

import io
import logging
import re

import pymupdf
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from personal_rag.ingestion.validation import InvalidFileError, decode_text
from personal_rag.schemas import Section

# Below this many characters per page, a PDF is treated as scanned images with no text layer.
MIN_CHARS_PER_PAGE = 100
MAX_PDF_PAGES = 500
HEADING_SEPARATOR = " > "
PLAIN_HEADING_MAX_CHARS = 60


logger = logging.getLogger(__name__)


class ScannedPdfError(InvalidFileError):
    """The PDF has (almost) no extractable text; OCR is not supported in version 1."""


class DocumentParseError(InvalidFileError):
    """The file passed signature checks but could not be parsed."""


class _HeadingPath:
    """Tracks the current heading hierarchy while walking a document in order."""

    def __init__(self) -> None:
        self._stack: list[tuple[int, str]] = []

    def push(self, level: int, title: str) -> str:
        # A new heading closes every open heading at the same or a deeper level.
        while self._stack and self._stack[-1][0] >= level:
            self._stack.pop()
        self._stack.append((level, title))
        return self.current  # type: ignore[return-value]

    @property
    def current(self) -> str | None:
        return HEADING_SEPARATOR.join(title for _, title in self._stack) or None


class _SectionBuilder:
    """Collects lines under the current heading and emits a Section when the heading changes."""

    def __init__(self) -> None:
        self.sections: list[Section] = []
        self._heading: str | None = None
        self._lines: list[str] = []

    def start(self, heading: str | None) -> None:
        self.flush()
        self._heading = heading

    def add(self, line: str) -> None:
        self._lines.append(line)

    def flush(self) -> None:
        text = "\n".join(self._lines).strip()
        if text:
            self.sections.append(Section(text=text, heading=self._heading))
        self._lines = []

    def finish(self) -> list[Section]:
        self.flush()
        return self.sections


def load_pdf(data: bytes) -> list[Section]:
    """One Section per page (1-based), built from text blocks so paragraphs stay separate."""
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        logger.warning("PDF parse failed: %s", type(exc).__name__)
        raise DocumentParseError("The PDF could not be read.") from None
    with doc:
        if doc.needs_pass:
            raise DocumentParseError("Password-protected PDFs are not supported.")
        if doc.page_count > MAX_PDF_PAGES:
            raise DocumentParseError(f"PDFs over {MAX_PDF_PAGES} pages are not supported.")
        pages: list[Section] = []
        for index, page in enumerate(doc, start=1):
            # sort=True gives reading order; block type 0 is text (1 is an image).
            blocks = [b[4].strip() for b in page.get_text("blocks", sort=True) if b[6] == 0]
            text = "\n\n".join(b for b in blocks if b)
            pages.append(Section(text=text, page=index))
        page_count = doc.page_count

    total_chars = sum(len(p.text.strip()) for p in pages)
    if page_count == 0 or total_chars / page_count < MIN_CHARS_PER_PAGE:
        raise ScannedPdfError(
            "This PDF has almost no extractable text. It looks scanned; "
            "OCR is not supported in version 1."
        )
    kept = [p for p in pages if p.text.strip()]
    if len(kept) < page_count:
        # Averages hide a mix of text and scanned pages; at least make the loss visible.
        skipped = page_count - len(kept)
        logger.warning("PDF has %d page(s) with no extractable text; skipped.", skipped)
    return kept


def _table_lines(table: Table) -> list[str]:
    lines = []
    for row in table.rows:
        cells: list[str] = []
        previous_tc = None
        for cell in row.cells:
            # python-docx repeats a merged cell once per grid column; keep it once.
            if cell._tc is previous_tc:
                continue
            previous_tc = cell._tc
            cells.append(" ".join(cell.text.split()))
        if any(cells):
            lines.append(" | ".join(cells))
    return lines


def _docx_heading_level(style_name: str) -> int | None:
    """Heading level for a paragraph style, or None when it is body text."""
    if style_name == "Title":
        return 0
    match = re.fullmatch(r"Heading\s*(\d+)", style_name)
    return int(match.group(1)) if match else None


def load_docx(data: bytes) -> list[Section]:
    """Walk body paragraphs and tables in document order; headings start new sections."""
    try:
        document = Document(io.BytesIO(data))
    except Exception as exc:
        logger.warning("DOCX parse failed: %s", type(exc).__name__)
        raise DocumentParseError("The DOCX file could not be read.") from None

    path = _HeadingPath()
    builder = _SectionBuilder()
    # Iterating body children (not document.paragraphs / document.tables) keeps tables in
    # their true position between paragraphs.
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if not text:
                continue
            level = _docx_heading_level(paragraph.style.name if paragraph.style else "")
            if level is not None:
                builder.start(path.push(level, text))
            else:
                builder.add(text)
        elif child.tag.endswith("}tbl"):
            for line in _table_lines(Table(child, document)):
                builder.add(line)
    return builder.finish()


_MD_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_LIST_ITEM_RE = re.compile(r"^\s*([-*+•]|\d+[.)])\s")


def _is_plain_heading(line: str, previous_blank: bool) -> bool:
    """Heuristic for headings in plain .txt files.

    A heading is a short line (under 60 characters) that is ALL CAPS or ends with a colon.
    We additionally require it to follow a blank line (or start the file) and not look like a
    list item, otherwise "Stack: Python" style lines inside a paragraph would split sections.
    """
    stripped = line.strip()
    if not stripped or len(stripped) >= PLAIN_HEADING_MAX_CHARS or not previous_blank:
        return False
    if _LIST_ITEM_RE.match(line):
        return False
    is_caps = any(c.isalpha() for c in stripped) and stripped.isupper()
    return is_caps or stripped.endswith(":")


def load_text(data: bytes, markdown: bool) -> list[Section]:
    """Split TXT/MD on headings: `#` headings for Markdown, the caps/colon heuristic for TXT."""
    path = _HeadingPath()
    builder = _SectionBuilder()
    in_fence = False
    previous_blank = True
    for line in decode_text(data).splitlines():
        if markdown:
            if _FENCE_RE.match(line):
                in_fence = not in_fence
            match = None if in_fence else _MD_HEADING_RE.match(line)
            if match:
                builder.start(path.push(len(match.group(1)), match.group(2).strip()))
                continue
        elif _is_plain_heading(line, previous_blank):
            title = line.strip().rstrip(":").strip()
            builder.start(path.push(1, title))
            previous_blank = False
            continue
        builder.add(line)
        previous_blank = not line.strip()
    return builder.finish()


def load_document(data: bytes, extension: str) -> list[Section]:
    """Dispatch on a validated, lower-case extension such as ".pdf"."""
    if extension == ".pdf":
        return load_pdf(data)
    if extension == ".docx":
        return load_docx(data)
    if extension in (".txt", ".md"):
        return load_text(data, markdown=extension == ".md")
    raise InvalidFileError(f"No loader for {extension}.")
