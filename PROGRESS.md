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

## Phase 2: Embeddings and storage (done, live smoke deferred)
Built: `llm/client.py` (client factory, 30 s timeout, 3 retries, `UpstreamError`),
`llm/embeddings.py` (`Embedder` Protocol, `OpenAIEmbedder`, batches of 100, order preserved,
token usage tracked), `store/vector_store.py` (Chroma `PersistentClient`, collection
`personal_kb`, cosine, model guard), `ingestion/service.py` (`IngestionService`: ingest with
dedupe/replace, delete, reindex), CLI `ingest`, `search`, `reindex`, `tests/fakes.py`
(hash-based `FakeEmbedder`).
Decisions:
- Chroma needs `embedding_function=None` (default would download a local ONNX model) and
  `configuration={"hnsw": {"space": "cosine"}}` for cosine (verified on chromadb 1.5.9).
- Replace order: embed new, write new, then delete old, so a failed embedding loses nothing.
- An empty index silently adopts a new embedding model; a non-empty one is blocked until `reindex`.
- `reindex` parses and embeds every original in `uploads/` (names are `{doc_id}_{name}`) BEFORE resetting the collection, so an API failure or empty uploads folder never wipes the index.
- Embedded-token figure printed by CLI is a tiktoken estimate of embed_text; the API-reported
  total is printed too.
- NOT DONE (needs API key): live `ingest`/`search` against the synthetic persona. When the key
  exists, run with a temp DATA_DIR, never ./data:
  `DATA_DIR=$(mktemp -d) uv run python -m personal_rag.cli ingest tests/fixtures/persona/*`
  (persona has ~690 chunk-text tokens, roughly 900 with headers, so cost is negligible).
Checks: ruff clean, 125 tests pass. (Code-review hook findings fixed: Chroma batch limit, reindex safety, CLI arg checks, filtered lookups.)

## Phase 3: Query pipeline (done, live ask smoke deferred)
Built: schemas (ScopeDecision, GroundedAnswer, GroundednessVerdict, TokenUsage, Source, DebugInfo,
AskResponse...), `llm/prompts.py` (spec prompts verbatim + groundedness prompt + message builders),
`llm/structured.py` (single `responses.parse` helper), `query/scope_guard.py`,
`query/retriever.py`, `query/generator.py` (+ optional groundedness checker),
`query/validator.py`, `query/pipeline.py`, `services.py` (composition root shared by CLI/API/evals),
CLI `ask [--debug]`, fakes for classifier/generator/groundedness, ~45 new tests.
Decisions:
- `responses.parse(..., store=False)`: personal documents are not retained by OpenAI.
- `temperature` and `reasoning={"effort": ...}` sent only when configured.
- Upstream failure at any step (classifier, embedder, generator, groundedness) -> status `error`.
  Planned API mapping: `/ask` returns HTTP 502 with the fixed-message AskResponse body in that case.
- Pipeline raises `InvalidQuestionError` (-> 400) and `IndexMismatchError` (-> 503); everything
  else is a response status. No-documents check happens before any OpenAI call.
- Excerpts and answers are defanged against delimiter tags (case/space-insensitive).
- Query-embedding tokens in debug are a tiktoken estimate (shared embedder counter is not
  request-safe). Question text is logged only at DEBUG, as the spec allows.
- NOT DONE (needs API key): `ask` smoke tests against the synthetic persona with a temp DATA_DIR.

## Phase 4: API (done)
Built: `api/main.py` (`create_app(context_factory)`, module-level `app` for uvicorn, lifespan loads
settings + services at startup so bad config fails fast with a value-free message),
`tests/integration/test_api.py` (36 tests: health, upload for all four formats, duplicate,
replace, list, delete, ask for each status, every error code 400/404/413/415/422/502/503, no
stack-trace leakage, filename sanitizing).
Decisions:
- Endpoints per spec section 10. Error bodies are `{"detail": ...}`; request-validation errors are
  mapped to a generic 400 (FastAPI's default 422 echoes input).
- `/ask` with an upstream failure returns HTTP 502 whose body is the fixed-message AskResponse
  (status `error`), so the UI can show it directly.
- Oversized uploads are rejected from the declared Content-Length before the body is buffered
  (middleware), with a bounded read in the endpoint as backstop for chunked/understated bodies.
  Writes (ingest/delete) are serialized with a lock held across embedding: acceptable for one local
  user; reads can briefly see old and new versions of a replaced file together.
- Missing `file` field -> 400; unknown or malformed doc_id on DELETE -> 404.
Dependency audit (`uv export` + `uvx pip-audit`, runtime deps, 2026-11-24):
- 5 advisories, all on chromadb 1.5.9: CVE-2026-45829, -45830, -45831, -45833 (aliases
  PYSEC-2026-311/3813/3814/3815). All describe the Chroma SERVER (REST endpoints, tenants, RBAC,
  trust_remote_code). This app uses the embedded `PersistentClient` and starts no Chroma server, so
  it is not exposed. No fixed version is published and the lock already has the latest chromadb,
  so no bump is possible. Revisit when a fix ships. No other vulnerable packages.
Checks: ruff clean, 202 tests pass.

## Phase 5: UI (done)
Built: `src/personal_rag/api_client.py` (httpx wrapper, error translation, no logic),
`ui/app.py` (Streamlit: sidebar with API health, multi-file uploader + "Add to knowledge base"
button, document list with delete buttons; chat with display-only history; colored status badges;
expandable Sources; "Show internals" toggle that sends `debug=true` and shows classifier
decision, every retrieved chunk vs threshold, latency, tokens), `tests/harness.py` (shared
fake-backed API context), `tests/integration/test_ui.py` (12 tests via Streamlit `AppTest`
against the real FastAPI app with fakes, plus ApiClient unit tests).
Decisions:
- The HTTP client lives in the package, not `ui/`, so it is importable/testable without Streamlit.
- UI reads only `API_BASE_URL` from the environment (it never loads settings or the API key).
- A 502 from `/ask` is rendered as a normal "Error" badge using the fixed message body.
- Streamlit server smoke-tested headless (health and index return 200).
Checks: ruff clean, 221 tests pass. (Review-hook fixes: flash messages survive rerun, malformed 200 bodies become ApiError, Markdown escaped in names.)

## Phase 6: Evaluation (harness DONE; live runs and tuning NOT DONE, need OPENAI_API_KEY)
Built: `evals/dataset.yaml` (54 cases: 19 answerable, 8 missing, 12 out_of_scope, 6 topic_overlap,
6 adversarial, 3 meta, written against the persona), `evals/cases.py` (schema/loader),
`evals/metrics.py` (pure formulas), `evals/report.py` (markdown report with spec 12.5 target
table), `evals/run_eval.py` (CLI: `--dataset --repeats --kb synthetic|real --yes --report-dir`),
tests: metrics, dataset sanity (incl. guard that no eval question appears in `src/`), harness
end to end with fakes (confirmation prompt, call estimate, temp data dir, report).
Decisions:
- `--kb synthetic` builds services against a TemporaryDirectory data dir (`Settings.model_copy`);
  the real DATA_DIR is never opened (a test asserts it is not even created).
- `--kb real` refuses the default dataset; use `--dataset evals/personal_dataset.yaml`.
- Report prints model IDs/tunables only (never the key or owner name). Query-embedding tokens
  in the report are tiktoken estimates; ingestion embedding tokens are API-reported.
- Threshold suggestion: if answerable and missing top-1 scores separate, report the gap;
  otherwise the cut that classifies the most runs correctly.
- must_include for date arithmetic uses "3 years" / "2 years"; if the model phrases it as
  words ("three years") that is a dataset brittleness to fix, not an app bug.
RESUME HERE once a key is in `.env` (user adds it at the end):
1. `uv run python -m evals.run_eval --yes --repeats 1` (writes evals/reports/<ts>.md)
2. Read failures + threshold suggestion. Up to 3 tuning iterations (SIMILARITY_THRESHOLD in
   .env.example default, then prompts in llm/prompts.py), re-running with --repeats 1 and
   recording before/after metrics here.
3. One final run with `--repeats 3`. Report tokens for every run.
4. Set `.env.example` SIMILARITY_THRESHOLD to the calibrated value and tell the user the value.
Checks: ruff clean, 260 tests pass. (Review fixes: errored runs counted, flagged and fail the exit code; harness reads committed persona files instead of importing tests; real-KB guard compares resolved paths.)
