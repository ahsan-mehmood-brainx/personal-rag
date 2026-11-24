"""Upload validation: types, signatures, size limits, filename sanitizing, doc IDs."""

import io
import zipfile

import pytest

from personal_rag.ingestion.validation import (
    FileTooLargeError,
    InvalidFileError,
    UnsupportedFileTypeError,
    compute_doc_id,
    sanitize_filename,
    validate_upload,
)

MAX = 1024 * 1024


def make_zip(names: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(name, "<x/>")
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("cv.pdf", "cv.pdf"),
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\me\\My CV (final).docx", "My_CV__final_.docx"),
        ("/abs/path/notes.md", "notes.md"),
        (".hidden.txt", "hidden.txt"),
        ("héllo wörld.txt", "h_llo_w_rld.txt"),
        ("", "upload"),
        ("///", "upload"),
    ],
)
def test_sanitize_filename(raw: str, expected: str) -> None:
    assert sanitize_filename(raw) == expected


def test_sanitize_filename_bounds_length_and_keeps_extension() -> None:
    result = sanitize_filename("a" * 300 + ".pdf")
    assert len(result) <= 100
    assert result.endswith(".pdf")


def test_doc_id_is_16_hex_chars_of_sha256() -> None:
    doc_id = compute_doc_id(b"hello")
    assert doc_id == "2cf24dba5fb0a30e"
    assert compute_doc_id(b"hello") == doc_id
    assert compute_doc_id(b"hello!") != doc_id


def test_accepts_each_supported_type() -> None:
    assert validate_upload("a.pdf", b"%PDF-1.7 rest", MAX).extension == ".pdf"
    docx = make_zip(["word/document.xml"])
    assert validate_upload("a.DOCX", docx, MAX).extension == ".docx"
    assert validate_upload("a.txt", b"plain text", MAX).extension == ".txt"
    assert validate_upload("a.md", "# café".encode(), MAX).extension == ".md"


def test_rejects_unsupported_extension() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        validate_upload("malware.exe", b"MZ", MAX)
    with pytest.raises(UnsupportedFileTypeError):
        validate_upload("noextension", b"data", MAX)


def test_rejects_oversized_file() -> None:
    with pytest.raises(FileTooLargeError):
        validate_upload("a.txt", b"x" * 11, 10)


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("fake.pdf", b"not a pdf"),
        ("fake.docx", b"not a zip"),
        ("fake.docx", make_zip(["other.xml"])),
        ("latin1.txt", "café".encode("latin-1")),
        ("empty.txt", b""),
    ],
)
def test_rejects_content_that_does_not_match_extension(name: str, data: bytes) -> None:
    with pytest.raises(InvalidFileError):
        validate_upload(name, data, MAX)


def test_utf8_bom_is_accepted() -> None:
    assert validate_upload("a.txt", b"\xef\xbb\xbfhello", MAX).safe_name == "a.txt"


def test_client_name_never_leaks_into_safe_name() -> None:
    result = validate_upload("../../x/secret.txt", b"hi", MAX)
    assert result.safe_name == "secret.txt"


def test_rejects_docx_that_expands_beyond_the_total_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("personal_rag.ingestion.validation.MAX_DOCX_UNCOMPRESSED_BYTES", 5)
    with pytest.raises(InvalidFileError, match="too large"):
        validate_upload("a.docx", make_zip(["word/document.xml", "word/styles.xml"]), MAX)
