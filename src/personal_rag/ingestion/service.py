"""Ingestion service: upload bytes to chunks, embeddings and the vector store.

Pipeline position: orchestrates the ingestion stages in order: validate, load, clean, chunk,
embed, store. `build_chunks` needs no network and is shared with the `preview` command.
`IngestionService` adds deduplication, replacement, deletion and reindexing on top.

Ordering is chosen so a failure never loses data: the new version is embedded and written
before the old version is removed.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from personal_rag.ingestion.chunking import chunk_document, count_tokens
from personal_rag.ingestion.cleaning import clean_sections
from personal_rag.ingestion.loaders import load_document
from personal_rag.ingestion.validation import InvalidFileError, ValidatedUpload, validate_upload
from personal_rag.llm.embeddings import Embedder
from personal_rag.schemas import Chunk, IngestResult
from personal_rag.store.vector_store import VectorStore

logger = logging.getLogger(__name__)

_DOC_ID_RE = re.compile(r"[0-9a-f]{16}")
_STORED_NAME_RE = re.compile(r"([0-9a-f]{16})_(.+)")


class EmptyDocumentError(InvalidFileError):
    """The file parsed but contained no text to index."""


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
    if not chunks:
        raise EmptyDocumentError("The document contains no text to index.")
    return upload, chunks


@dataclass
class ReindexResult:
    documents: int = 0
    chunks: int = 0
    embedded_tokens: int = 0
    failed: list[str] = field(default_factory=list)
    skipped_reset: bool = False  # True when there were no originals, so the index was kept


class IngestionService:
    def __init__(
        self,
        *,
        embedder: Embedder,
        store: VectorStore,
        uploads_dir: Path,
        max_bytes: int,
        chunk_size: int,
        overlap: int,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._uploads_dir = uploads_dir
        self._max_bytes = max_bytes
        self._chunk_size = chunk_size
        self._overlap = overlap

    def _stored_path(self, doc_id: str, safe_name: str) -> Path:
        return self._uploads_dir / f"{doc_id}_{safe_name}"

    def ingest(self, filename: str, data: bytes) -> IngestResult:
        """Ingest one upload: `ingested`, `duplicate` (no-op) or `replaced`."""
        self._store.require_usable()
        upload, chunks = build_chunks(
            filename,
            data,
            max_bytes=self._max_bytes,
            chunk_size=self._chunk_size,
            overlap=self._overlap,
            embedding_model=self._embedder.model,
        )

        existing = self._store.get_document(upload.doc_id)
        if existing is not None:
            logger.info("ingest status=duplicate doc_id=%s", upload.doc_id)
            return IngestResult(
                doc_id=upload.doc_id,
                filename=existing.filename,
                status="duplicate",
                chunk_count=existing.chunk_count,
            )

        previous = [
            d for d in self._store.find_by_filename(upload.safe_name) if d.doc_id != upload.doc_id
        ]
        embedded_tokens = sum(count_tokens(c.embed_text) for c in chunks)
        # Embed first: if this fails, the old version is untouched.
        vectors = self._embedder.embed_documents([c.embed_text for c in chunks])

        self._uploads_dir.mkdir(parents=True, exist_ok=True)
        path = self._stored_path(upload.doc_id, upload.safe_name)
        path.write_bytes(data)
        try:
            self._store.add_chunks(chunks, vectors)
        except Exception:
            path.unlink(missing_ok=True)
            raise

        for old in previous:
            self.delete(old.doc_id)
        status = "replaced" if previous else "ingested"
        logger.info("ingest status=%s doc_id=%s chunks=%d", status, upload.doc_id, len(chunks))
        return IngestResult(
            doc_id=upload.doc_id,
            filename=upload.safe_name,
            status=status,
            chunk_count=len(chunks),
            embedded_tokens=embedded_tokens,
        )

    def delete(self, doc_id: str) -> bool:
        """Remove a document's chunks and stored original. False if it was not indexed."""
        if not _DOC_ID_RE.fullmatch(doc_id):
            return False  # also keeps arbitrary strings out of the glob below
        removed = self._store.delete_document(doc_id)
        for path in self._uploads_dir.glob(f"{doc_id}_*"):
            path.unlink(missing_ok=True)
        return removed > 0

    def reindex(self) -> ReindexResult:
        """Re-embed every stored original with the configured model into a fresh index.

        Everything is parsed and embedded before the old index is touched, so an API failure or
        an empty uploads folder never leaves the knowledge base empty.
        """
        result = ReindexResult()
        prepared: list[tuple[Path, ValidatedUpload, list[Chunk], list[list[float]]]] = []
        originals = sorted(self._uploads_dir.glob("*")) if self._uploads_dir.exists() else []
        for path in originals:
            match = _STORED_NAME_RE.fullmatch(path.name)
            if not match or not path.is_file():
                continue
            try:
                upload, chunks = build_chunks(
                    match.group(2),
                    path.read_bytes(),
                    max_bytes=self._max_bytes,
                    chunk_size=self._chunk_size,
                    overlap=self._overlap,
                    embedding_model=self._embedder.model,
                )
            except Exception as exc:  # one unreadable file must not abort the rebuild
                logger.warning("reindex skipped %s: %s", path.name, type(exc).__name__)
                result.failed.append(path.name)
                continue
            # An embedding failure propagates on purpose: nothing has been modified yet.
            vectors = self._embedder.embed_documents([c.embed_text for c in chunks])
            result.embedded_tokens += sum(count_tokens(c.embed_text) for c in chunks)
            prepared.append((path, upload, chunks, vectors))

        if not prepared:
            result.skipped_reset = True
            return result

        self._store.reset()
        for _, _, chunks, vectors in prepared:
            self._store.add_chunks(chunks, vectors)
            result.documents += 1
            result.chunks += len(chunks)
        return result
