# Progress log

Resume rule: read this file, then `git log --oneline`, then continue with the first phase not listed
as done. Run `uv run ruff check .` and `uv run pytest` at the end of every phase.

## Standing state
- OPENAI_API_KEY was not set in `.env` when work started (user will add it at the end).
  All live steps (Phase 2 embed/search smoke, Phase 3 ask smoke, Phase 6 eval runs) are
  deferred until the key exists. Offline work proceeds normally.
- Interpreter: native arm64 CPython 3.12 (`.python-version` = 3.12).

## Phase 0: Scaffold (done)
- uv project, src layout, pinned deps, ruff config, `.gitignore`, `.env.example`, `config.py`,
  `messages.py`, README skeleton.
- Post-approval changes: `.python-version` -> `3.12`, arm64 confirmed. Added
  `CLASSIFIER_REASONING_EFFORT` / `GENERATION_REASONING_EFFORT` (default `low`, values verified in
  installed openai 3.57.0: none, minimal, low, medium, high, xhigh, max). They are sent to the
  Responses API as `reasoning={"effort": ...}` only when not None.
- Checks: ruff clean, 16 tests pass.
