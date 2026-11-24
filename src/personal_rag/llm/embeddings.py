"""Embedding client behind a Protocol.

Pipeline position: ingestion embeds chunk `embed_text`; the query pipeline embeds the question
with the same model, so both live in one vector space. The `Embedder` Protocol lets tests
inject a deterministic fake and keeps the pipeline free of OpenAI imports.
"""

import logging
from typing import Protocol

from openai import OpenAI, OpenAIError

from personal_rag.llm.client import UpstreamError

logger = logging.getLogger(__name__)

MAX_BATCH_SIZE = 100


class Embedder(Protocol):
    """Anything that can turn text into vectors, in input order."""

    model: str
    tokens_used: int  # cumulative tokens reported by the API (0 for fakes)

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class OpenAIEmbedder:
    """Embedder backed by the OpenAI embeddings API."""

    def __init__(self, client: OpenAI, model: str) -> None:
        self._client = client
        self.model = model
        self.tokens_used = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), MAX_BATCH_SIZE):
            vectors.extend(self._embed_batch(texts[start : start + MAX_BATCH_SIZE]))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed_batch([text])[0]

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        try:
            response = self._client.embeddings.create(model=self.model, input=batch)
        except OpenAIError as exc:
            logger.error("Embedding request failed: %s", type(exc).__name__)
            raise UpstreamError("The embedding request failed.") from None
        if len(response.data) != len(batch):
            raise UpstreamError("The embedding response did not match the request.")
        if response.usage is not None:
            self.tokens_used += response.usage.total_tokens
        # The API tags each vector with its input index; sort to guarantee input order.
        return [item.embedding for item in sorted(response.data, key=lambda d: d.index)]
