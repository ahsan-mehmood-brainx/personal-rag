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

## Phase 1: Ingestion without OpenAI (done)
Built: `schemas.py` (Section, Chunk), `ingestion/validation.py`, `loaders.py`, `cleaning.py`,
`chunking.py`, `service.build_chunks`, `cli.py preview`, persona fixtures
(`tests/fixtures/persona/{cv.md,projects.txt,certifications.docx,cv_onepage.pdf}` +
`make_fixtures.py`), tests/conftest.py, 69 new unit tests.
Decisions:
- Headings are hierarchical paths ("Jordan Avery > Experience > Northwind Analytics, ...") for
  DOCX and Markdown; plain TXT headings (short, ALL CAPS or trailing colon) must also follow a
  blank line and not look like a list item, to avoid false splits.
- PDF: one Section per page, built from text blocks (paragraphs stay separate). No heading detection.
- Chunker split ladder: paragraph, then line (keeps CV bullets whole), then sentence, then token
  window. Overlap uses whole trailing pieces only.
- Small-section merge keeps both headings ("A / B"), or just the child path if one is the parent.
- Text decode uses `utf-8-sig` (accepts UTF-8 and strips a BOM).
- tiktoken downloads cl100k_base once from OpenAI's public blob store and caches it; tests need
  that cache (first run needs network).
- `preview` uses `.env` chunk settings when complete, else spec defaults (works without API key).
Checks: ruff clean, 85 tests pass. Preview run on all four persona files.
