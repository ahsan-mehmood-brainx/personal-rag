---
diff_hash: f225f5a83dc5ebb0fd0ae6b8caa28f878d12eac1c35e5290dd0c13c657dbd39b
reviewed_at: 2026-11-24T12:44:42Z
---

## Summary

Initial scaffold of the personal-rag project (Python 3.12, uv, pydantic-settings): settings loader with value-free error reporting, fixed refusal/meta messages, `.env.example`, `.gitignore`, spec/progress docs, and unit tests. No stack marker matched (Python, no NestJS/React/Express/Rails/PHP/Flutter/iOS/Android), so a generic review was applied. No secrets or PII found in the diff; `.env` is ignored and only `.env.example` is staged.

## Findings

### Critical (0)

### High (0)

### Medium (2)
- **src/personal_rag/config.py:62** — `classifier_reasoning_effort` and `generation_reasoning_effort` default to `"low"`, and `env_ignore_empty=True` turns a blank variable into that default. The `None` value ("do not send reasoning") therefore cannot be reached from the environment, even though the comments and PROGRESS.md say it is sent "only when not None". `.env.example` also ships `gpt-4o-mini` with `*_REASONING_EFFORT=low`; the file's own comment says these apply to reasoning models only. Once the LLM layer sends `reasoning={"effort": ...}`, non-reasoning models will likely be rejected by the API, with no config-only way to opt out. *(correctness)*
  - status: open
  - dev_reasoning: N/A
  - ai_reasoning: Make the default `None` (and keep "low" in `.env.example` only if a reasoning model is the default), or add an explicit sentinel such as `off`/`none` that maps to omitted. `test_reasoning_effort_defaults_to_low_and_is_overridable` currently locks in the blank-falls-back-to-"low" behavior and would need updating. The spec only requires omit-when-unset for temperature, so this also diverges from the established pattern.

- **src/personal_rag/config.py:10** — `DEFAULT_ENV_FILE = Path(".env")` is resolved against the current working directory. Running the API or Streamlit UI from another directory silently skips the `.env` and reports "missing required setting(s)", and `DATA_DIR=./data` has the same CWD dependence (the index could be created in an unexpected location). *(maintainability)*
  - status: skipped
  - dev_reasoning: Single-user local tool launched from the repo root; README documents this. Anchoring DATA_DIR to the package location would break the temp-dir override the eval harness relies on.
  - ai_reasoning: Anchor to the project root (for example `Path(__file__).resolve().parents[2] / ".env"`) or document that the app must be launched from the repo root. The data dir should be resolved the same way, since it holds personal documents and the vector index.

### Low (1)
- **src/personal_rag/config.py:73** — `api_base_url` is a plain `str` with no validation, while every other field is constrained. A typo such as a missing scheme will only fail at the first request. *(consistency)*
  - status: open
  - dev_reasoning: N/A
  - ai_reasoning: Use `pydantic.AnyHttpUrl` or a validator checking for an http(s) scheme.

## Reviewed files
- .env.example
- .gitignore
- .python-version
- PERSONAL_RAG_SPEC.md
- PROGRESS.md
- README.md
- pyproject.toml
- src/personal_rag/__init__.py
- src/personal_rag/api/__init__.py
- src/personal_rag/config.py
- src/personal_rag/ingestion/__init__.py
- src/personal_rag/llm/__init__.py
- src/personal_rag/messages.py
- src/personal_rag/query/__init__.py
- src/personal_rag/store/__init__.py
- tests/__init__.py
- tests/integration/__init__.py
- tests/unit/__init__.py
- tests/unit/test_config.py
- tests/unit/test_messages.py
- uv.lock (skimmed: dependency lockfile only; pinned versions in pyproject.toml could not be independently verified against the package index in this run)
