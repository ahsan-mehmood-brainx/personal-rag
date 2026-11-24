"""ChromaDB wrapper: one persistent collection with cosine distance.

Pipeline position: the storage layer between ingestion (writes chunks and vectors) and the
query pipeline (reads nearest chunks). The document list is derived from chunk metadata, so
there is no second database to keep in sync.

Embedding-model guard: the collection records which embedding model built it. Vectors from
different models are not comparable, so if the configured model differs, `usable` is False and
callers must refuse to answer until `reindex` rebuilds the index.
"""

import logging
from pathlib import Path
from typing import Any

import chromadb

from personal_rag.schemas import Chunk, DocumentInfo, RetrievedChunk

logger = logging.getLogger(__name__)

COLLECTION_NAME = "personal_kb"
UNKNOWN_PAGE = -1  # Chroma metadata cannot hold None


class IndexMismatchError(RuntimeError):
    """The index was built with a different embedding model. The API maps this to HTTP 503."""


class VectorStore:
    def __init__(self, chroma_dir: Path, embedding_model: str) -> None:
        chroma_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(chroma_dir))
        self._embedding_model = embedding_model
        self._collection = self._open_collection()

    def _open_collection(self) -> Any:
        # embedding_function=None: we always supply vectors. Chroma's default function would
        # otherwise try to download a local model.
        collection = self._client.get_or_create_collection(
            COLLECTION_NAME,
            embedding_function=None,
            configuration={"hnsw": {"space": "cosine"}},
            metadata={"embedding_model": self._embedding_model},
        )
        stored = (collection.metadata or {}).get("embedding_model")
        if stored != self._embedding_model and collection.count() == 0:
            # Nothing is indexed, so there is nothing to be incompatible with.
            collection.modify(metadata={"embedding_model": self._embedding_model})
        return collection

    # --- index status -----------------------------------------------------------------

    @property
    def stored_embedding_model(self) -> str | None:
        return (self._collection.metadata or {}).get("embedding_model")

    @property
    def usable(self) -> bool:
        """False when the index was built with a different embedding model."""
        return self.stored_embedding_model == self._embedding_model

    def require_usable(self) -> None:
        if not self.usable:
            raise IndexMismatchError(
                "The index was built with a different embedding model. "
                "Run `uv run python -m personal_rag.cli reindex` to rebuild it."
            )

    def chunk_count(self) -> int:
        return int(self._collection.count())

    def is_empty(self) -> bool:
        return self.chunk_count() == 0

    # --- writes -----------------------------------------------------------------------

    def add_chunks(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")
        if not chunks:
            return
        # Chroma rejects a single add larger than its max batch size (about 5k on 1.5.9).
        step = self._client.get_max_batch_size()
        for start in range(0, len(chunks), step):
            batch = chunks[start : start + step]
            self._collection.add(
                ids=[c.chunk_id for c in batch],
                embeddings=embeddings[start : start + step],
                documents=[c.text for c in batch],
                metadatas=[self._metadata(c) for c in batch],
            )

    @staticmethod
    def _metadata(chunk: Chunk) -> dict[str, str | int]:
        return {
            "chunk_id": chunk.chunk_id,
            "doc_id": chunk.doc_id,
            "filename": chunk.filename,
            "section": chunk.section,
            "page": chunk.page if chunk.page is not None else UNKNOWN_PAGE,
            "chunk_index": chunk.chunk_index,
            "token_count": chunk.token_count,
            "ingested_at": chunk.ingested_at,
            "embedding_model": chunk.embedding_model,
        }

    def delete_document(self, doc_id: str) -> int:
        """Delete every chunk of a document; returns how many were removed."""
        existing = self._collection.get(where={"doc_id": doc_id}, include=[])["ids"]
        if existing:
            self._collection.delete(ids=existing)
        return len(existing)

    def reset(self) -> None:
        """Drop the collection and recreate it empty for the configured embedding model."""
        self._client.delete_collection(COLLECTION_NAME)
        self._collection = self._open_collection()

    # --- reads ------------------------------------------------------------------------

    def query(self, embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        """Nearest chunks, best first. Similarity is 1 - cosine distance."""
        count = self.chunk_count()
        if count == 0:
            return []
        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=min(top_k, count),
            include=["documents", "metadatas", "distances"],
        )
        retrieved = []
        for text, meta, distance in zip(
            result["documents"][0], result["metadatas"][0], result["distances"][0], strict=True
        ):
            page = int(meta["page"])
            retrieved.append(
                RetrievedChunk(
                    chunk_id=str(meta["chunk_id"]),
                    filename=str(meta["filename"]),
                    section=str(meta["section"]),
                    page=None if page == UNKNOWN_PAGE else page,
                    text=text,
                    similarity=1.0 - float(distance),
                )
            )
        return retrieved

    def list_documents(self) -> list[DocumentInfo]:
        """Documents derived from chunk metadata, oldest first."""
        return self._documents(None)

    def _documents(self, where: dict[str, str] | None) -> list[DocumentInfo]:
        metadatas = self._collection.get(where=where, include=["metadatas"])["metadatas"] or []
        docs: dict[str, DocumentInfo] = {}
        for meta in metadatas:
            doc_id = str(meta["doc_id"])
            if doc_id in docs:
                docs[doc_id].chunk_count += 1
            else:
                docs[doc_id] = DocumentInfo(
                    doc_id=doc_id,
                    filename=str(meta["filename"]),
                    chunk_count=1,
                    ingested_at=str(meta["ingested_at"]),
                )
        return sorted(docs.values(), key=lambda d: (d.ingested_at, d.filename))

    def get_document(self, doc_id: str) -> DocumentInfo | None:
        found = self._documents({"doc_id": doc_id})
        return found[0] if found else None

    def find_by_filename(self, filename: str) -> list[DocumentInfo]:
        return self._documents({"filename": filename})
