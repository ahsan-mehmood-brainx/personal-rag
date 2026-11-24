"""Deterministic fakes for tests: embedder (and, from Phase 3, classifier and generator).

The fake embedder uses the hashing trick on lower-cased words, so texts that share words get
high cosine similarity. That is crude but real enough to exercise retrieval, thresholds and
ranking without any network call.
"""

import hashlib
import math
import re

DIMENSIONS = 256


def _vector(text: str) -> list[float]:
    vector = [0.0] * DIMENSIONS
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        bucket = int(hashlib.md5(word.encode(), usedforsecurity=False).hexdigest(), 16)
        vector[bucket % DIMENSIONS] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class FakeEmbedder:
    """Implements the `Embedder` protocol and records every call for assertions."""

    def __init__(self, model: str = "fake-embedding-model") -> None:
        self.model = model
        self.tokens_used = 0
        self.document_calls: list[list[str]] = []
        self.query_calls: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_calls.append(list(texts))
        return [_vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        return _vector(text)
