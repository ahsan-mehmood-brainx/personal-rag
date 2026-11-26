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


# --- Query pipeline ---------------------------------------------------------------------

# `web_answered` is returned only when the caller allowed external search and the scope gate
# classified the question as out of scope; the answer then comes from a web search.
Status = Literal[
    "answered", "not_found", "out_of_scope", "web_answered", "meta", "no_documents", "error"
]


class TokenUsage(BaseModel):
    """Tokens reported by the API for one call. Zeros when the API reports nothing."""

    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0  # already included in output_tokens; shown separately for cost

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
        )

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class ScopeDecision(BaseModel):
    """Structured output of the scope classifier (gate 1)."""

    category: Literal["personal", "meta", "out_of_scope"]
    reason: str  # one sentence, for the debug view and logs


class GroundedAnswer(BaseModel):
    """Structured output of the generator."""

    status: Literal["answered", "not_found"]
    answer: str
    citations: list[str]  # labels such as ["S1", "S3"]


class GroundednessVerdict(BaseModel):
    """Structured output of the optional groundedness check."""

    supported: bool
    unsupported_claims: list[str]


class LabeledChunk(BaseModel):
    """A retrieved chunk with the label (S1, S2, ...) the generator sees instead of its ID."""

    label: str
    chunk: RetrievedChunk


class Source(BaseModel):
    label: str
    filename: str
    section: str
    page: int | None
    similarity: float
    excerpt: str  # first ~300 characters of the chunk


class WebSource(BaseModel):
    """A web page a `web_answered` answer cited."""

    title: str
    url: str


class WebAnswer(BaseModel):
    """Output of the external web search step."""

    answer: str
    sources: list[WebSource] = Field(default_factory=list)


class DebugChunk(BaseModel):
    """A retrieved chunk as shown in the debug view, kept or not."""

    chunk_id: str
    filename: str
    section: str
    page: int | None
    similarity: float
    kept: bool  # similarity >= threshold


class DebugInfo(BaseModel):
    classifier_category: str | None = None
    classifier_reason: str | None = None
    retrieved: list[DebugChunk] = Field(default_factory=list)
    threshold: float
    latency_ms: dict[str, float] = Field(default_factory=dict)
    token_usage: dict[str, TokenUsage] = Field(default_factory=dict)


class AskResponse(BaseModel):
    status: Status
    answer: str
    sources: list[Source] = Field(default_factory=list)  # only chunks the answer cited
    web_sources: list[WebSource] = Field(default_factory=list)  # only for `web_answered`
    debug: DebugInfo | None = None
