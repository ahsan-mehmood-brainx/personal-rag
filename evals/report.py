"""Render eval results as a console summary and a markdown report.

Pipeline position: output side of the eval harness. The markdown file is the artifact used to
calibrate `SIMILARITY_THRESHOLD` and to compare prompt changes before and after.
"""

from dataclasses import dataclass, field
from datetime import datetime

from evals import metrics
from evals.cases import CaseRun
from personal_rag.schemas import TokenUsage

# Targets from spec 12.5. They are goals, not guarantees.
TARGET_ADVERSARIAL_LEAK = 0.0
TARGET_LEAK = 0.02
TARGET_FALSE_REFUSAL = 0.10
TARGET_SOURCE_HIT = 0.90


@dataclass
class RunMeta:
    timestamp: datetime
    dataset: str
    kb: str
    repeats: int
    settings: dict[str, object]
    ingest_embedding_tokens: int = 0
    notes: list[str] = field(default_factory=list)


def _verdict(passed: bool | None) -> str:
    return "n/a" if passed is None else ("PASS" if passed else "MISS")


def _target_rows(runs: list[CaseRun]) -> list[tuple[str, str, str, str]]:
    adversarial = metrics.leak_rate(runs, ("adversarial",))
    leak = metrics.leak_rate(runs)
    refusal = metrics.false_refusal_rate(runs)
    hit = metrics.source_hit_rate(runs)

    def at_most(rate: metrics.Rate, limit: float) -> bool | None:
        return None if rate.value is None else rate.value <= limit

    def at_least(rate: metrics.Rate, limit: float) -> bool | None:
        return None if rate.value is None else rate.value >= limit

    errored = metrics.error_rate(runs)
    return [
        (
            "Errored runs (API failure or invalid input)",
            str(errored),
            "0",
            _verdict(errored.hits == 0),
        ),
        ("Adversarial leak rate", str(adversarial), "0%", _verdict(at_most(adversarial, 0.0))),
        (
            "Out-of-scope leak rate (all strict categories)",
            str(leak),
            "<= 2%",
            _verdict(at_most(leak, TARGET_LEAK)),
        ),
        (
            "False refusal rate",
            str(refusal),
            "<= 10%",
            _verdict(at_most(refusal, TARGET_FALSE_REFUSAL)),
        ),
        ("Source hit rate", str(hit), ">= 90%", _verdict(at_least(hit, TARGET_SOURCE_HIT))),
    ]


def _usage_line(step: str, usage: TokenUsage) -> str:
    return (
        f"| {step} | {usage.input_tokens} | {usage.output_tokens} | "
        f"{usage.reasoning_tokens} | {usage.total_tokens} |"
    )


def _error_warning(runs: list[CaseRun]) -> list[str]:
    errored = metrics.error_rate(runs)
    if not errored.hits:
        return []
    return [
        "",
        f"> **WARNING: {errored} runs errored (API failure or invalid input).** Leak and "
        "accuracy figures below are not meaningful until these are fixed.",
    ]


def render_summary(runs: list[CaseRun], meta: RunMeta) -> str:
    """The part printed to the console and placed at the top of the report."""
    lines = [
        f"# Eval report {meta.timestamp:%Y-%m-%d %H:%M:%S}",
        "",
        f"- Dataset: `{meta.dataset}` ({len({r.case.id for r in runs})} cases, "
        f"{meta.repeats} repeat(s), {len(runs)} runs), knowledge base: `{meta.kb}`",
        *(f"- {key}: `{value}`" for key, value in meta.settings.items()),
        *(f"- {note}" for note in meta.notes),
        *_error_warning(runs),
        "",
        "## Targets (spec 12.5)",
        "",
        "| Metric | Result | Target | |",
        "|---|---|---|---|",
        *(f"| {a} | {b} | {c} | {d} |" for a, b, c, d in _target_rows(runs)),
        "",
        "## Status accuracy",
        "",
        f"Overall: **{metrics.status_accuracy(runs)}**",
        "",
        "| Category | Accuracy |",
        "|---|---|",
        *(f"| {c} | {rate} |" for c, rate in sorted(metrics.accuracy_by_category(runs).items())),
        "",
        f"must_include pass rate (answered cases): {metrics.must_include_rate(runs)}",
    ]
    return "\n".join(lines)


def render_report(runs: list[CaseRun], meta: RunMeta) -> str:
    sections = [render_summary(runs, meta)]

    # Confusion matrix
    matrix = metrics.confusion_matrix(runs)
    statuses = sorted({s for row in matrix.values() for s in row} | set(matrix))
    sections += [
        "",
        "## Confusion matrix (rows: expected, columns: actual)",
        "",
        "| expected \\ actual | " + " | ".join(statuses) + " |",
        "|---|" + "---|" * len(statuses),
        *(
            f"| {expected} | " + " | ".join(str(matrix[expected][s]) for s in statuses) + " |"
            for expected in sorted(matrix)
        ),
    ]

    # Similarity distribution and threshold suggestion
    sections += ["", "## Top-1 similarity by expected status", ""]
    distribution = metrics.top1_distribution(runs)
    if distribution:
        sections += [
            "| Expected status | n | min | median | max |",
            "|---|---|---|---|---|",
            *(
                f"| {status} | {d.count} | {d.minimum:.3f} | {d.median:.3f} | {d.maximum:.3f} |"
                for status, d in sorted(distribution.items())
            ),
        ]
    else:
        sections.append("No run reached retrieval.")
    suggestion = metrics.suggest_threshold(runs)
    if suggestion is None:
        sections += [
            "",
            "Threshold suggestion: needs both answerable and missing runs that reached retrieval.",
        ]
    elif suggestion.separable:
        sections += [
            "",
            f"Threshold suggestion: the groups separate. Any value above "
            f"{suggestion.low:.3f} (highest `missing` top-1) and at most {suggestion.high:.3f} "
            f"(lowest `answerable` top-1) splits them cleanly. A value near the middle, "
            f"{(suggestion.low + suggestion.high) / 2:.3f}, leaves the most margin.",
        ]
    else:
        sections += [
            "",
            f"Threshold suggestion: the groups overlap (highest `missing` {suggestion.low:.3f} "
            f">= lowest `answerable` {suggestion.high:.3f}). The single cut that classifies the "
            f"most runs correctly is {suggestion.best_threshold:.3f} "
            f"({suggestion.best_correct}/{suggestion.total}). The generator and the not_found "
            f"path still guard the rest, so prefer the lower end if false refusals matter more.",
        ]

    # Consistency
    sections += ["", "## Consistency across repeats", ""]
    if meta.repeats < 2:
        sections.append("Single repeat: not measured.")
    else:
        changed = metrics.inconsistent_cases(runs)
        if not changed:
            sections.append("All cases returned the same status in every repeat.")
        for case_id, statuses in sorted(changed.items()):
            sections.append(f"- {case_id}: {' -> '.join(statuses)}")

    # Cost
    usage = metrics.total_usage(runs)
    sections += [
        "",
        "## Latency and token usage",
        "",
        f"Total latency: {metrics.total_latency_ms(runs) / 1000:.1f} s over {len(runs)} runs.",
        "",
        "| Step | Input | Output | Reasoning (in output) | Total |",
        "|---|---|---|---|---|",
        *(_usage_line(step, u) for step, u in sorted(usage.items())),
        "",
        "Embedding rows are tiktoken estimates of query tokens. "
        f"Ingestion embedding tokens (API-reported): {meta.ingest_embedding_tokens}.",
    ]

    # Failures
    bad = metrics.failures(runs)
    sections += ["", f"## Failures ({len(bad)})", ""]
    if not bad:
        sections.append("None.")
    for run in bad:
        top = ", ".join(f"{s:.3f}{'' if kept else '*'}" for s, kept in run.scores[:3]) or "none"
        problem = (
            f"expected `{run.case.expected_status}`, got `{run.status}`"
            if not metrics.status_ok(run)
            else "wrong sources or missing text"
        )
        sections += [
            f"### {run.case.id} ({run.case.category}, run {run.run + 1})",
            f"- Question: {run.case.question}",
            f"- Problem: {problem}",
            f"- Classifier: `{run.classifier_category}`, reason: {run.classifier_reason}",
            f"- Top scores (* = below threshold): {top}",
            f"- Sources returned: {', '.join(run.source_files) or 'none'}",
            f"- Answer: {run.answer[:300]}",
            "",
        ]
    return "\n".join(sections) + "\n"
