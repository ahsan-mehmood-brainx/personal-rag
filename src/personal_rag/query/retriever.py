"""Gate 2: the evidence gate (similarity threshold).

Pipeline position: after the scope gate. The question is embedded with the same model as the
documents, the nearest `top_k` chunks are fetched, and only chunks whose cosine similarity is at
least the threshold count as evidence. If none do, the pipeline answers `not_found` without
calling the generator. The threshold is calibrated from the eval report.
"""

from dataclasses import dataclass

from personal_rag.llm.embeddings import Embedder
from personal_rag.schemas import LabeledChunk, RetrievedChunk
from personal_rag.store.vector_store import VectorStore


@dataclass
class RetrievalResult:
    all_hits: list[RetrievedChunk]  # everything the store returned, best first
    kept: list[LabeledChunk]  # hits at or above the threshold, labeled S1..Sn

    @property
    def top_score(self) -> float | None:
        return self.all_hits[0].similarity if self.all_hits else None


def retrieve(
    question: str,
    *,
    embedder: Embedder,
    store: VectorStore,
    top_k: int,
    threshold: float,
) -> RetrievalResult:
    hits = store.query(embedder.embed_query(question), top_k)
    kept = [
        LabeledChunk(label=f"S{number}", chunk=hit)
        for number, hit in enumerate((h for h in hits if h.similarity >= threshold), start=1)
    ]
    return RetrievalResult(all_hits=hits, kept=kept)
