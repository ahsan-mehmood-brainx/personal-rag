"""Ingestion service: upload bytes to chunks (and, from Phase 2, to embeddings and the store).

Pipeline position: orchestrates the ingestion stages in order: validate, load, clean, chunk,
embed, store. `build_chunks` is the part that needs no network and is shared by the `preview`
command and by the real ingestion path.
"""

from datetime import UTC, datetime

from personal_rag.ingestion.chunking import chunk_document
from personal_rag.ingestion.cleaning import clean_sections
from personal_rag.ingestion.loaders import load_document
from personal_rag.ingestion.validation import ValidatedUpload, validate_upload
from personal_rag.schemas import Chunk


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def build_chunks(
    filename: str,
    data: bytes,
    *,
    max_bytes: int,
    chunk_size: int,
    overlap: int,
    embedding_model: str,
) -> tuple[ValidatedUpload, list[Chunk]]:
    """Validate, parse, clean and chunk one file. Raises UploadError subclasses on bad input."""
    upload = validate_upload(filename, data, max_bytes)
    sections = clean_sections(load_document(data, upload.extension))
    chunks = chunk_document(
        doc_id=upload.doc_id,
        filename=upload.safe_name,
        sections=sections,
        chunk_size=chunk_size,
        overlap=overlap,
        embedding_model=embedding_model,
        ingested_at=utc_now_iso(),
    )
    return upload, chunks
