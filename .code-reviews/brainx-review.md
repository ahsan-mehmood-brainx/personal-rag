---
diff_hash: ead0f019b7e9a1735f976987cd2c7c5950ec90b07c089f20ee3de7971b79d800
reviewed_at: 2026-11-26T10:38:25Z
stack: unknown
---

## Summary

Adds opt-in external web search. `POST /ask` accepts `allow_external_search`; when it is true and the scope gate classifies a question as `out_of_scope`, the pipeline answers with an OpenAI Responses `web_search` call (new `query/web_search.py`) and returns status `web_answered` with `web_sources`. Personal questions still go through retrieval and the grounded generator, and the web model sees only the question. The React frontend unlocks the "Allow External Search" toggle, sends it per question, renders a "From the web" badge and http(s)-only source links, and drops the "Show internals" toggle. Tests cover pipeline routing, the API, the searcher, the client, storage migration and e2e. All five findings were fixed in this pass; after the fixes, pytest (271), frontend lint, typecheck, vitest (40) and the chat Playwright suite (36) pass.

Stack: no root marker matches (the root is a Python/FastAPI project), so the backend got a generic review; `web/` was reviewed against the React criteria. Backend and frontend live in this one repo, and the request/response contract (`allow_external_search`, `web_answered`, `web_sources`) matches on both sides.

## Findings

### Critical (0)

### High (0)

### Medium (2)
- **src/personal_rag/query/web_search.py:103-108** — `_strip_spans` removes citation spans one by one on the shrinking string. Duplicate or overlapping `url_citation` annotations (two URLs on one inline citation) make the second removal cut into real answer text. *(correctness)*
  - status: fixed
  - dev_reasoning: N/A
  - ai_reasoning: `_strip_spans` now drops out-of-range spans, merges duplicate and overlapping ones, then removes the merged spans from the end, so each removal indexes the original text. The searcher test now passes a duplicated citation, and `test_overlapping_citation_spans_are_merged` covers partial overlaps.
- **src/personal_rag/query/web_search.py:53** — The web search call inherits the shared client's 30 s timeout and 3 retries. Web search with reasoning often runs past 30 s, and the worst case (4 x 30 s plus the scope call) exceeds the frontend's 120 s ask timeout, so the UI gives up while the backend keeps retrying and spending tokens. *(correctness)*
  - status: fixed
  - dev_reasoning: N/A
  - ai_reasoning: The searcher now calls `client.with_options(timeout=45, max_retries=1)` (`WEB_SEARCH_TIMEOUT_SECONDS`, `WEB_SEARCH_MAX_RETRIES`), so its worst case is 90 s and the whole request stays inside the frontend's 120 s ask timeout. The other calls keep the shared 30 s / 3-retry client. The searcher test asserts the options.

### Low (3)
- **src/personal_rag/query/web_search.py:65-68** — A response with status `incomplete` (for example cut off by the content filter) is returned as a normal `web_answered` answer if it has any text. *(correctness)*
  - status: fixed
  - dev_reasoning: N/A
  - ai_reasoning: The searcher raises `UpstreamError` when `response.status` is not `completed`, so the pipeline returns `error` instead of a partial answer. Covered by `test_web_search_incomplete_response_is_upstream_error`.
- **web/src/features/chat/ResponseDetails.tsx:49-62** — `WebSourcesList` keys items by the normalized href, but different raw URLs can normalize to the same href (`https://a.com` and `https://a.com/`), producing duplicate React keys and a repeated link. *(correctness)*
  - status: fixed
  - dev_reasoning: N/A
  - ai_reasoning: Added `toWebLinks`, which parses each URL once, keeps only http(s), and dedupes on the normalized href before rendering; the hostname is reused instead of parsed again. ChatPage.test now includes `https://KUBERNETES.io/docs/` and still expects one web source.
- **src/personal_rag/cli.py:156-171** — The `ask` command cannot enable external search and does not print `web_sources`, so the CLI falls behind the API and web client for the new status. *(consistency)*
  - status: fixed
  - dev_reasoning: N/A
  - ai_reasoning: `ask` gained `--external-search` (passed as `allow_external_search`) and prints each web source as `web: <title> | <url>`, matching how document sources are printed.

## Reviewed files
- README.md
- src/personal_rag/api/main.py
- src/personal_rag/api_client.py
- src/personal_rag/llm/prompts.py
- src/personal_rag/query/pipeline.py
- src/personal_rag/query/web_search.py (new)
- src/personal_rag/schemas.py
- src/personal_rag/services.py
- src/personal_rag/cli.py (changed during this review)
- tests/fakes.py, tests/harness.py, tests/integration/test_api.py, tests/unit/test_llm_calls.py, tests/unit/test_pipeline.py
- web/README.md, web/e2e/chat.spec.ts, web/e2e/fake_api_server.py
- web/src/api/client.ts, client.test.ts, guards.ts, types.ts, web/src/config.ts
- web/src/features/chat/ (ChatContext, ChatPage, ChatPage.test, ExternalSearchToggle + css, MessageItem, ResponseDetails + css, chat.test, conversationStore, statusMeta, types)
- web/src/test/fakeBackend.ts
