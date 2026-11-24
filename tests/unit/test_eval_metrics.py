"""Eval metrics: every formula checked against handcrafted runs."""

import pytest
from evals import metrics
from evals.cases import CaseRun, EvalCase
from evals.report import RunMeta, render_report

from personal_rag.schemas import TokenUsage


def case(case_id: str, category: str, expected: str, sources=(), include=()) -> EvalCase:
    return EvalCase(
        id=case_id,
        category=category,
        question=f"question {case_id}",  # type: ignore[arg-type]
        expected_status=expected,
        expected_sources=list(sources),
        must_include=list(include),  # type: ignore[arg-type]
    )


def run(
    c: EvalCase, status: str, answer="", sources=(), scores=(), repeat=0, usage=None
) -> CaseRun:
    return CaseRun(
        case=c,
        run=repeat,
        status=status,
        answer=answer,
        source_files=list(sources),
        scores=list(scores),
        usage=usage or {},
        latency_ms=100.0,
    )


ANS = case("a1", "answerable", "answered", ["cv.md"], ["Northwind"])
ANS2 = case("a2", "answerable", "answered", ["cv.md", "projects.txt"], ["AWS"])
MISS = case("m1", "missing", "not_found")
OOS = case("o1", "out_of_scope", "out_of_scope")
TRAP = case("t1", "topic_overlap", "out_of_scope")
ADV = case("v1", "adversarial", "out_of_scope")


def test_status_accuracy_and_per_category() -> None:
    runs = [
        run(ANS, "answered"),
        run(ANS2, "not_found"),
        run(OOS, "out_of_scope"),
        run(TRAP, "answered"),
    ]
    assert metrics.status_accuracy(runs).value == pytest.approx(0.5)
    by_category = metrics.accuracy_by_category(runs)
    assert by_category["answerable"].value == pytest.approx(0.5)
    assert by_category["out_of_scope"].value == 1.0
    assert by_category["topic_overlap"].value == 0.0


def test_confusion_matrix_counts() -> None:
    runs = [run(ANS, "answered"), run(ANS2, "not_found"), run(ANS, "not_found")]
    matrix = metrics.confusion_matrix(runs)
    assert matrix["answered"]["answered"] == 1
    assert matrix["answered"]["not_found"] == 2


def test_leak_rate_counts_answered_in_strict_categories_only() -> None:
    runs = [
        run(OOS, "answered"),
        run(TRAP, "out_of_scope"),
        run(ADV, "out_of_scope"),
        run(ANS, "answered"),
        run(MISS, "answered"),
    ]
    leak = metrics.leak_rate(runs)
    assert (leak.hits, leak.total) == (1, 3)
    assert metrics.leak_rate(runs, ("adversarial",)).hits == 0


def test_false_refusal_rate() -> None:
    runs = [
        run(ANS, "answered"),
        run(ANS, "not_found"),
        run(ANS2, "out_of_scope"),
        run(ANS2, "error"),
        run(OOS, "out_of_scope"),
    ]
    rate = metrics.false_refusal_rate(runs)
    assert (rate.hits, rate.total) == (2, 4)  # errors are failures but not "refusals"


def test_source_hit_requires_every_expected_source() -> None:
    runs = [
        run(ANS, "answered", sources=["cv.md"]),
        run(ANS2, "answered", sources=["cv.md"]),
        run(ANS2, "answered", sources=["projects.txt", "cv.md", "extra.md"]),
    ]
    rate = metrics.source_hit_rate(runs)
    assert (rate.hits, rate.total) == (2, 3)


def test_source_hit_ignores_cases_without_expected_sources() -> None:
    open_ended = case("a3", "answerable", "answered")
    assert metrics.source_hit_rate([run(open_ended, "answered")]).total == 0
    assert metrics.source_hit_rate([]).value is None


def test_must_include_is_case_insensitive_and_answered_only() -> None:
    runs = [
        run(ANS, "answered", "I worked at NORTHWIND."),
        run(ANS, "answered", "I worked somewhere."),
        run(ANS, "not_found", "Northwind"),
    ]
    rate = metrics.must_include_rate(runs)
    assert (rate.hits, rate.total) == (1, 2)


def test_top1_distribution_by_expected_status() -> None:
    runs = [
        run(ANS, "answered", scores=[(0.6, True), (0.5, True)]),
        run(ANS2, "answered", scores=[(0.4, True)]),
        run(MISS, "not_found", scores=[(0.2, False)]),
        run(OOS, "out_of_scope"),
    ]  # never reached retrieval: excluded
    dist = metrics.top1_distribution(runs)
    assert (dist["answered"].minimum, dist["answered"].median, dist["answered"].maximum) == (
        0.4,
        0.5,
        0.6,
    )
    assert dist["not_found"].count == 1
    assert "out_of_scope" not in dist


def test_threshold_suggestion_when_groups_separate() -> None:
    runs = [
        run(ANS, "answered", scores=[(0.60, True)]),
        run(ANS2, "answered", scores=[(0.45, True)]),
        run(MISS, "not_found", scores=[(0.25, False)]),
        run(case("m2", "missing", "not_found"), "not_found", scores=[(0.30, False)]),
    ]
    suggestion = metrics.suggest_threshold(runs)
    assert suggestion is not None
    assert suggestion.separable
    assert (suggestion.low, suggestion.high) == (0.30, 0.45)
    assert 0.30 < suggestion.best_threshold <= 0.45
    assert suggestion.best_correct == suggestion.total == 4


def test_threshold_suggestion_when_groups_overlap() -> None:
    runs = [
        run(ANS, "answered", scores=[(0.60, True)]),
        run(ANS2, "answered", scores=[(0.28, True)]),
        run(MISS, "not_found", scores=[(0.35, True)]),
        run(case("m2", "missing", "not_found"), "not_found", scores=[(0.20, False)]),
    ]
    suggestion = metrics.suggest_threshold(runs)
    assert suggestion is not None and not suggestion.separable
    assert suggestion.best_correct == 3  # one of the four must be sacrificed


def test_threshold_suggestion_needs_both_groups() -> None:
    assert metrics.suggest_threshold([run(ANS, "answered", scores=[(0.5, True)])]) is None


def test_inconsistent_cases_across_repeats() -> None:
    runs = [
        run(ANS, "answered", repeat=0),
        run(ANS, "not_found", repeat=1),
        run(OOS, "out_of_scope", repeat=0),
        run(OOS, "out_of_scope", repeat=1),
    ]
    assert metrics.inconsistent_cases(runs) == {"a1": ["answered", "not_found"]}


def test_failures_include_wrong_status_missing_text_and_wrong_sources() -> None:
    good = run(ANS, "answered", "Northwind", sources=["cv.md"])
    wrong_status = run(OOS, "answered")
    missing_text = run(ANS, "answered", "nothing", sources=["cv.md"])
    wrong_sources = run(ANS, "answered", "Northwind", sources=["projects.txt"])
    assert metrics.failures([good, wrong_status, missing_text, wrong_sources]) == [
        wrong_status,
        missing_text,
        wrong_sources,
    ]


def test_usage_and_latency_totals() -> None:
    usage = {"scope": TokenUsage(input_tokens=10, output_tokens=5, reasoning_tokens=2)}
    runs = [run(ANS, "answered", usage=usage), run(ANS, "answered", usage=usage)]
    assert metrics.total_usage(runs)["scope"].input_tokens == 20
    assert metrics.total_usage(runs)["scope"].reasoning_tokens == 4
    assert metrics.total_latency_ms(runs) == 200.0


def test_report_renders_all_sections() -> None:
    from datetime import datetime

    runs = [
        run(ANS, "answered", "Northwind", ["cv.md"], [(0.6, True)]),
        run(MISS, "not_found", scores=[(0.2, False)]),
        run(OOS, "answered", "leaked answer"),
    ]
    meta = RunMeta(datetime(2026, 1, 1), "evals/dataset.yaml", "synthetic", 1, {"TOP_K": 5})
    text = render_report(runs, meta)
    for heading in (
        "## Targets",
        "## Status accuracy",
        "## Confusion matrix",
        "## Top-1 similarity",
        "## Consistency",
        "## Latency and token usage",
        "## Failures (1)",
    ):
        assert heading in text
    assert "leaked answer" in text
    assert "MISS" in text  # the leak target is missed
