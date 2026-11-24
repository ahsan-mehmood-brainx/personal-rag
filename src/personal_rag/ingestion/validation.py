"""Upload validation: file type, signature, size, filename sanitizing and document IDs.

Pipeline position: the first gate of ingestion. Nothing is parsed or stored until the bytes
pass these checks. The client-provided filename is never used as a path; only the sanitized
form returned here is.
"""

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass

ALLOWED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")
MAX_SAFE_NAME_LENGTH = 100
# A DOCX is a ZIP; refuse ones that would expand absurdly (zip-bomb guard). The cap applies to
# the sum of all members, since styles, media and other XML parts can carry the bomb too.
MAX_DOCX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024


class UploadError(ValueError):
    """Base class for rejected uploads. `status_code` is the HTTP code the API maps it to."""

    status_code = 400


class UnsupportedFileTypeError(UploadError):
    status_code = 415


class FileTooLargeError(UploadError):
    status_code = 413


class InvalidFileError(UploadError):
    """Extension is allowed but the content does not look like that file type."""

    status_code = 422


@dataclass(frozen=True)
class ValidatedUpload:
    safe_name: str
    extension: str
    doc_id: str


def sanitize_filename(name: str) -> str:
    """Return a filesystem-safe name: no path parts, only [A-Za-z0-9._-], bounded length."""
    # Handle both separators regardless of the server OS: clients may send Windows paths.
    base = re.split(r"[\\/]", name)[-1]
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base).lstrip(".")
    if len(base) > MAX_SAFE_NAME_LENGTH:
        stem, dot, ext = base.rpartition(".")
        if dot and len(ext) <= 5:
            base = stem[: MAX_SAFE_NAME_LENGTH - len(ext) - 1] + "." + ext
        else:
            base = base[:MAX_SAFE_NAME_LENGTH]
    return base or "upload"


def compute_doc_id(data: bytes) -> str:
    """First 16 hex characters of the SHA-256 of the file bytes."""
    return hashlib.sha256(data).hexdigest()[:16]


def get_extension(safe_name: str) -> str:
    return "." + safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""


def decode_text(data: bytes) -> str:
    """Decode TXT/MD bytes as UTF-8.

    `utf-8-sig` accepts plain UTF-8 as well and also strips a leading byte-order mark, so one
    decode covers both cases the spec allows. Anything else is rejected, not guessed at.
    """
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InvalidFileError("Text files must be UTF-8 encoded.") from None


def _check_docx_signature(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            archive.getinfo("word/document.xml")
            total = sum(info.file_size for info in archive.infolist())
    except (zipfile.BadZipFile, KeyError):
        raise InvalidFileError("File is not a valid DOCX document.") from None
    if total > MAX_DOCX_UNCOMPRESSED_BYTES:
        raise InvalidFileError("DOCX content is too large to process.")


def validate_upload(filename: str, data: bytes, max_bytes: int) -> ValidatedUpload:
    """Validate an upload and return its safe name, extension and doc_id.

    Raises UnsupportedFileTypeError (415), FileTooLargeError (413) or InvalidFileError (422).
    """
    safe_name = sanitize_filename(filename)
    extension = get_extension(safe_name)
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}."
        )
    if len(data) > max_bytes:
        raise FileTooLargeError(f"File is larger than the {max_bytes // (1024 * 1024)} MB limit.")
    if not data:
        raise InvalidFileError("File is empty.")

    if extension == ".pdf":
        if not data.startswith(b"%PDF"):
            raise InvalidFileError("File is not a valid PDF.")
    elif extension == ".docx":
        _check_docx_signature(data)
    else:
        decode_text(data)

    return ValidatedUpload(safe_name=safe_name, extension=extension, doc_id=compute_doc_id(data))
