"""Deterministic fakes for tests: embedder (and, from Phase 3, classifier and generator).

The fake embedder uses the hashing trick on lower-cased words, so texts that share words get
high cosine similarity. That is crude but real enough to exercise retrieval, thresholds and
ranking without any network call.
"""

import hashlib
import math
import re
from datetime import date

from personal_rag.schemas import (
    GroundedAnswer,
    GroundednessVerdict,
    LabeledChunk,
    ScopeDecision,
    TokenUsage,
)

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


# --- Phase 3: classifier, generator, groundedness -----------------------------------------

FAKE_USAGE = TokenUsage(input_tokens=10, output_tokens=5, reasoning_tokens=2)


class FakeClassifier:
    """Returns a fixed category (or raises) and records the questions it saw."""

    def __init__(self, category: str = "personal", raises: Exception | None = None) -> None:
        self.category = category
        self.raises = raises
        self.calls: list[str] = []

    def classify(self, question: str) -> tuple[ScopeDecision, TokenUsage]:
        self.calls.append(question)
        if self.raises:
            raise self.raises
        decision = ScopeDecision(category=self.category, reason="fake reason")  # type: ignore[arg-type]
        return decision, FAKE_USAGE


class FakeGenerator:
    """Returns a preset GroundedAnswer (a callable may build it from the excerpts)."""

    def __init__(self, answer: GroundedAnswer | None = None, raises: Exception | None = None):
        self.answer = answer or GroundedAnswer(
            status="answered", answer="Fake answer.", citations=["S1"]
        )
        self.raises = raises
        self.calls: list[tuple[str, list[LabeledChunk], date]] = []

    def generate(
        self, question: str, excerpts: list[LabeledChunk], today: date
    ) -> tuple[GroundedAnswer, TokenUsage]:
        self.calls.append((question, excerpts, today))
        if self.raises:
            raise self.raises
        return self.answer, FAKE_USAGE


class FakeGroundednessChecker:
    def __init__(self, supported: bool = True, raises: Exception | None = None) -> None:
        self.supported = supported
        self.raises = raises
        self.calls = 0

    def check(
        self, answer: str, excerpts: list[LabeledChunk]
    ) -> tuple[GroundednessVerdict, TokenUsage]:
        self.calls += 1
        if self.raises:
            raise self.raises
        claims = [] if self.supported else ["an unsupported claim"]
        return GroundednessVerdict(supported=self.supported, unsupported_claims=claims), FAKE_USAGE
