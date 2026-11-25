"""Eval metrics: pure functions over lists of `CaseRun`.

Pipeline position: between the runner (which collects raw outcomes) and the report (which
formats them). Nothing here touches the network, so every formula is unit-tested.

Definitions follow spec 12.4:
- Out-of-scope leak rate: share of out_of_scope, topic_overlap and adversarial runs that came
  back `answered`. The most important strictness metric.
- False refusal rate: answerable runs that came back `not_found` or `out_of_scope`.
- Source hit rate: answerable runs with expected sources where every expected file appears.
- must_include pass rate: answered runs with must_include where every string appears.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import median

from evals.cases import STRICT_CATEGORIES, CaseRun
from personal_rag.schemas import TokenUsage


@dataclass(frozen=True)
class Rate:
    hits: int
    total: int

    @property
    def value(self) -> float | None:
        return self.hits / self.total if self.total else None

    def __str__(self) -> str:
        return "n/a" if self.value is None else f"{self.value:.1%} ({self.hits}/{self.total})"


def status_ok(run: CaseRun) -> bool:
    return run.status == run.case.expected_status


def sources_ok(run: CaseRun) -> bool:
    return all(name in run.source_files for name in run.case.expected_sources)


def must_include_ok(run: CaseRun) -> bool:
    answer = run.answer.lower()
    return all(text.lower() in answer for text in run.case.must_include)


def status_accuracy(runs: list[CaseRun]) -> Rate:
    return Rate(sum(status_ok(r) for r in runs), len(runs))


def accuracy_by_category(runs: list[CaseRun]) -> dict[str, Rate]:
    groups: dict[str, list[CaseRun]] = defaultdict(list)
    for run in runs:
        groups[run.case.category].append(run)
    return {category: status_accuracy(group) for category, group in groups.items()}


def confusion_matrix(runs: list[CaseRun]) -> dict[str, Counter[str]]:
    matrix: dict[str, Counter[str]] = defaultdict(Counter)
    for run in runs:
        matrix[run.case.expected_status][run.status] += 1
    return matrix


def error_rate(runs: list[CaseRun]) -> Rate:
    """Runs that ended in `error` or `invalid_input`: upstream trouble, not a quality signal."""
    return Rate(sum(r.status in ("error", "invalid_input") for r in runs), len(runs))


def leak_rate(runs: list[CaseRun], categories: tuple[str, ...] = STRICT_CATEGORIES) -> Rate:
    strict = [r for r in runs if r.case.category in categories]
    return Rate(sum(r.status == "answered" for r in strict), len(strict))


def false_refusal_rate(runs: list[CaseRun]) -> Rate:
    answerable = [r for r in runs if r.case.category == "answerable"]
    return Rate(sum(r.status in ("not_found", "out_of_scope") for r in answerable), len(answerable))


def source_hit_rate(runs: list[CaseRun]) -> Rate:
    relevant = [r for r in runs if r.case.category == "answerable" and r.case.expected_sources]
    return Rate(sum(sources_ok(r) for r in relevant), len(relevant))


def must_include_rate(runs: list[CaseRun]) -> Rate:
    relevant = [r for r in runs if r.status == "answered" and r.case.must_include]
    return Rate(sum(must_include_ok(r) for r in relevant), len(relevant))


@dataclass(frozen=True)
class Distribution:
    count: int
    minimum: float
    median: float
    maximum: float


def top1_distribution(runs: list[CaseRun]) -> dict[str, Distribution]:
    """Top-1 similarity split by expected status. Only runs that reached retrieval count."""
    scores: dict[str, list[float]] = defaultdict(list)
    for run in runs:
        if run.top1 is not None:
            scores[run.case.expected_status].append(run.top1)
    return {
        status: Distribution(len(values), min(values), median(values), max(values))
        for status, values in scores.items()
    }


@dataclass(frozen=True)
class ThresholdSuggestion:
    separable: bool
    low: float | None  # highest top-1 among `missing` cases
    high: float | None  # lowest top-1 among `answerable` cases
    best_threshold: float | None
    best_correct: int
    total: int


def suggest_threshold(runs: list[CaseRun]) -> ThresholdSuggestion | None:
    """Where do answerable and missing top-1 scores separate?

    If every missing score is below every answerable score, any threshold between them is a
    clean split (`low` to `high`). Otherwise the groups overlap, and `best_threshold` is the
    single cut that classifies the most runs correctly (answerable >= t, missing < t).
    """

    def scores(expected: str) -> list[float]:
        return [r.top1 for r in runs if r.case.expected_status == expected and r.top1 is not None]

    answerable, missing = scores("answered"), scores("not_found")
    if not answerable or not missing:
        return None
    low, high = max(missing), min(answerable)

    points = sorted({*answerable, *missing})
    candidates = [(a + b) / 2 for a, b in zip(points, points[1:], strict=False)] or points
    candidates += [points[0] - 0.01, points[-1] + 0.01]

    def correct(threshold: float) -> int:
        return sum(s >= threshold for s in answerable) + sum(s < threshold for s in missing)

    best = max(candidates, key=lambda t: (correct(t), -abs(t - (low + high) / 2)))
    return ThresholdSuggestion(
        separable=low < high,
        low=low,
        high=high,
        best_threshold=best,
        best_correct=correct(best),
        total=len(answerable) + len(missing),
    )


def inconsistent_cases(runs: list[CaseRun]) -> dict[str, list[str]]:
    """Case ID -> statuses seen across repeats, for cases whose status changed between runs."""
    seen: dict[str, list[str]] = defaultdict(list)
    for run in runs:
        seen[run.case.id].append(run.status)
    return {case_id: statuses for case_id, statuses in seen.items() if len(set(statuses)) > 1}


def has_problem(run: CaseRun) -> bool:
    """True for a wrong status, or an answer that misses expected sources or must_include text."""
    if not status_ok(run):
        return True
    if run.status != "answered":
        return False
    missing_sources = bool(run.case.expected_sources) and not sources_ok(run)
    missing_text = bool(run.case.must_include) and not must_include_ok(run)
    return missing_sources or missing_text


def failures(runs: list[CaseRun]) -> list[CaseRun]:
    return [run for run in runs if has_problem(run)]


def total_usage(runs: list[CaseRun]) -> dict[str, TokenUsage]:
    """Token usage summed per pipeline step across all runs."""
    totals: dict[str, TokenUsage] = {}
    for run in runs:
        for step, usage in run.usage.items():
            totals[step] = totals.get(step, TokenUsage()) + usage
    return totals


def total_latency_ms(runs: list[CaseRun]) -> float:
    return sum(r.latency_ms for r in runs)
