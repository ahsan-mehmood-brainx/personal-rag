---
diff_hash: 8a51892e1a7a26218c24318976d6a073bedbd34548ced1a8b7096654d805be07
reviewed_at: 2026-11-24T13:03:49Z
---

## Summary

Phase 4 adds the FastAPI app (`api/main.py`: health, upload, list, delete, ask, error mapping, write lock), 36 integration tests, and PROGRESS.md notes. No stack marker matched (Python project, no package.json/Gemfile/etc.), so a generic review was done (correctness, security, consistency, maintainability). The design is clean: value-free error bodies, generic 400 for validation errors, doc_id validated before any glob, filename sanitizing tested. Two items are worth a look.

## Findings

### Critical (0)

### High (0)

### Medium (2)
- **src/personal_rag/api/main.py:166** — The upload size cap is applied only after Starlette has parsed the whole multipart body. `file.file.read(max_upload_bytes + 1)` limits what is passed to ingestion, but the full request is already spooled to memory/disk by then. An oversized upload is still fully buffered before the 413. PROGRESS.md describes this as "capped before parsing", which overstates the protection. *(security)*
  - status: open
  - dev_reasoning: N/A
  - ai_reasoning: Check Content-Length against max_upload_bytes (plus multipart overhead) before reading, or add a small ASGI middleware that rejects oversized bodies. Reword the PROGRESS.md note either way. Exposure is limited if the server binds only to 127.0.0.1 as documented, which is why this is Medium and not High.
- **src/personal_rag/api/main.py:164-171** — The write lock is held during the whole ingest, including the OpenAI embedding call (network I/O, retries). Every concurrent upload or delete waits behind it, and /ask and /health do not take the lock, so reads can run against a half-updated index during replace (delete old, add new). *(correctness)*
  - status: skipped
  - dev_reasoning: Single-user local tool; serialized writes held across embedding are an accepted trade-off, and replace adds the new version before deleting the old so reads never see an empty document.
  - ai_reasoning: Either document that reads are intentionally unlocked and the replace window is accepted, or use a reader/writer pattern. Consider embedding outside the lock and locking only the store mutation.

### Low (1)
- **tests/integration/test_api.py:203** — The test function signature is about 101 characters, longer than the lines the surrounding tests wrap. It may exceed the configured line length if ruff's limit is 100. *(consistency)*
  - status: skipped
  - dev_reasoning: False positive: ruff (line-length 100) passes.
  - ai_reasoning: Wrap the parameters like the neighboring tests. Ignore this if ruff is already clean at the configured limit (PROGRESS.md says it is).

## Reviewed files
- PROGRESS.md
- src/personal_rag/api/main.py
- tests/integration/test_api.py
