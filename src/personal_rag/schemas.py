"""Pydantic models shared across the pipeline.

Pipeline position: these are the data shapes that flow between stages. Ingestion produces
`Section` objects (loaders) and `Chunk` objects (chunker); the query pipeline produces
`AskResponse`. Keeping them in one module makes the whole data flow readable in one place.
"""

from typing import Literal

from pydantic import BaseModel, Field


class Section(BaseModel):
    """A contiguous piece of a document under one heading (or one PDF page)."""

    text: str
    heading: str | None = None
    # 1-based page number for PDFs; None for formats without pages.
    page: int | None = None


class Chunk(BaseModel):
    """One embeddable unit of a document, plus the metadata stored beside its vector."""

    chunk_id: str  # "{doc_id}:{chunk_index}"
    doc_id: str
    filename: str
    section: str  # heading, or "General" when the document has none here
    page: int | None  # None is stored as -1 because Chroma metadata cannot hold None
    chunk_index: int
    token_count: int
    ingested_at: str  # ISO 8601, UTC
    embedding_model: str
    text: str = Field(description="Raw chunk text, shown to the user and sent to the generator.")
    embed_text: str = Field(description="Header plus text. This is what gets embedded.")


class RetrievedChunk(BaseModel):
    """A chunk returned by a vector search, with its cosine similarity to the query."""

    chunk_id: str
    filename: str
    section: str
    page: int | None
    text: str
    similarity: float  # 1 - cosine distance; higher is closer


class DocumentInfo(BaseModel):
    """One indexed document, derived from chunk metadata (there is no separate database)."""

    doc_id: str
    filename: str
    chunk_count: int
    ingested_at: str


class IngestResult(BaseModel):
    doc_id: str
    filename: str
    status: Literal["ingested", "duplicate", "replaced"]
    chunk_count: int
    embedded_tokens: int = 0  # estimate (tiktoken) of tokens sent for embedding; 0 if skipped
