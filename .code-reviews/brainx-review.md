---
diff_hash: 71b0975abe55d17dd50551c53652f4ec97a49e360d27a3f149cfb4194c7bb210
reviewed_at: 2026-11-24T13:14:30Z
---

## Summary

Phase 6 adds the evaluation harness: a 54-case YAML dataset, a pydantic case schema/loader, pure metric functions, a markdown report renderer, a CLI runner (`evals/run_eval.py`) with a cost confirmation and a temp-dir synthetic knowledge base, and unit/integration tests using fakes. Stack: no marker matched (Python), so a generic review was applied. No secrets, injection or unsafe-deserialization issues found (`yaml.safe_load` is used, the report omits the API key, reports and the personal dataset are gitignored). One correctness concern: upstream failures are recorded as non-leaks, so an outage can produce a passing report.

## Findings

### Critical (0)

### High (0)

### Medium (1)
- **evals/run_eval.py:72** — `run_cases` catches `UpstreamError` and `IndexMismatchError` together with `InvalidQuestionError` and records every one as `status="invalid_input"`, then continues with exit code 0. A bad or expired API key, a rate limit or an outage turns the whole run into "invalid_input" rows. `leak_rate` only counts `answered`, so the report shows Adversarial and Out-of-scope leak rate as 0% PASS, and the threshold calibration is computed from nothing. Failed runs also skip the progress line. *(correctness)*
  - status: open
  - dev_reasoning: N/A
  - ai_reasoning: Treat only `InvalidQuestionError` as a recordable outcome. For `UpstreamError`/`IndexMismatchError`, record a distinct status (for example `error`), print it in progress, count errored runs in the report header, mark the target rows `n/a` or `MISS` when errors exist, and return a non-zero exit code (or abort after N consecutive upstream errors to avoid spending money on a dead key).

### Low (2)
- **evals/run_eval.py:24** — The runner, which lives in the `evals` package, imports `tests.fixtures.make_fixtures`. A non-test tool depends on the test tree, which only works when run from the repo root with `tests` importable. *(consistency)*
  - status: open
  - dev_reasoning: N/A
  - ai_reasoning: Acceptable for a dev-only harness, but consider moving the persona builder to a shared module (for example `evals/persona.py`) that both `tests` and `evals` import.
- **evals/run_eval.py:139** — The guard that stops `--kb real` from using the default dataset compares `Path` objects, so an absolute path or `evals/../evals/dataset.yaml` to the same file bypasses it. The result is synthetic-persona questions run against the real index, which wastes API spend and yields a meaningless report. *(correctness)*
  - status: open
  - dev_reasoning: N/A
  - ai_reasoning: Compare `args.dataset.resolve()` with `DEFAULT_DATASET.resolve()`.

## Reviewed files
- .code-reviews/brainx-review.md (deleted, previous review replaced)
- PROGRESS.md
- pyproject.toml
- evals/__init__.py
- evals/cases.py
- evals/dataset.yaml
- evals/metrics.py
- evals/report.py
- evals/run_eval.py
- tests/integration/test_eval_harness.py
- tests/unit/test_eval_dataset.py (skimmed)
- tests/unit/test_eval_metrics.py (skimmed)
