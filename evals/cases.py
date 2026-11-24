"""Eval dataset schema and loader.

Pipeline position: input side of the eval harness. Cases live in YAML, never in application
code; the app must pass them on its merits, with no special-casing.
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

from personal_rag.schemas import Status, TokenUsage

Category = Literal["answerable", "missing", "out_of_scope", "topic_overlap", "adversarial", "meta"]

# Categories whose correct outcome is a refusal. An `answered` here is a leak.
STRICT_CATEGORIES: tuple[str, ...] = ("out_of_scope", "topic_overlap", "adversarial")


class EvalCase(BaseModel):
    id: str
    category: Category
    question: str
    expected_status: Status
    expected_sources: list[str] = Field(default_factory=list)
    must_include: list[str] = Field(default_factory=list)


class CaseRun(BaseModel):
    """The outcome of asking one case once."""

    case: EvalCase
    run: int
    status: str  # a pipeline Status, or "invalid_input" when the pipeline rejected the question
    answer: str
    source_files: list[str] = Field(default_factory=list)
    classifier_category: str | None = None
    classifier_reason: str | None = None
    # (similarity, kept) for every retrieved chunk, best first. Empty when retrieval never ran.
    scores: list[tuple[float, bool]] = Field(default_factory=list)
    latency_ms: float = 0.0
    usage: dict[str, TokenUsage] = Field(default_factory=dict)

    @property
    def top1(self) -> float | None:
        return self.scores[0][0] if self.scores else None


class DatasetError(ValueError):
    """The dataset file is missing, malformed, or contains duplicate IDs."""


def load_cases(path: Path) -> list[EvalCase]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DatasetError(f"Cannot read dataset {path}: {exc.strerror}") from None
    except yaml.YAMLError:
        raise DatasetError(f"{path} is not valid YAML.") from None
    if not isinstance(raw, list) or not raw:
        raise DatasetError(f"{path} must contain a non-empty list of cases.")
    try:
        cases = [EvalCase(**item) for item in raw]
    except (TypeError, ValidationError) as exc:
        raise DatasetError(f"{path} has an invalid case: {exc}") from None
    ids = [c.id for c in cases]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise DatasetError(f"Duplicate case IDs: {', '.join(duplicates)}")
    return cases
