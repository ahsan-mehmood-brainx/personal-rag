---
diff_hash: 3c6577478ecaed461c777cdd8b9cd552a49392a2d0a730785069436dc60ab7e3
reviewed_at: 2026-11-24T13:09:16Z
---

## Summary

Phase 5 adds a Streamlit UI (`ui/app.py`), an httpx-based `ApiClient` in the package, a shared test `Harness` extracted from the API tests, and AppTest-based UI tests. Stack: no marker matched (Python/FastAPI/Streamlit), so a generic review was applied. No secrets, injection or auth issues found; the UI holds no API key. Findings concern lost user feedback and unhandled malformed responses.

## Findings

### Critical (0)

### High (0)

### Medium (1)
- **ui/app.py:76** — Upload results and delete errors are rendered with `st.sidebar.success/error` and then `st.rerun()` is called immediately (also line 93), which discards the script run's elements. The user never sees per-file upload status (including failures such as unsupported type, too large, or scanned PDF) or a failed delete message. *(correctness)*
  - status: open
  - dev_reasoning: N/A
  - ai_reasoning: Store the messages in `st.session_state` before `st.rerun()` and render them (then clear them) at the top of the sidebar on the next run. The current tests do not cover this path, which is why they pass.

### Low (2)
- **src/personal_rag/api_client.py:72** — A 200 response with an unexpected body (missing key, non-JSON, wrong item shape) raises `KeyError`, `ValueError` or `ValidationError` from `health()`, `list_documents()` and `upload()` (lines 72, 82, 92). These are not `ApiError`, so the UI's `except (ApiError, ApiUnavailableError)` does not catch them and the Streamlit page shows a stack trace. `ask()` already handles this case. *(consistency)*
  - status: open
  - dev_reasoning: N/A
  - ai_reasoning: Wrap parsing in try/except (`ValueError`, `KeyError`, `TypeError`, `ValidationError`) and raise `ApiError` with a generic detail, as `ask()` does.
- **ui/app.py:91** — Document filenames (user-controlled) are interpolated into `st.markdown` with `**...**`, so names containing markdown syntax render oddly or inject links/images. No HTML execution, so impact is cosmetic. *(maintainability)*
  - status: open
  - dev_reasoning: N/A
  - ai_reasoning: Escape markdown in the filename, or render it with `st.text`/`st.write` of a plain string with `unsafe_allow_html` left off and special characters escaped.

## Reviewed files
- .code-reviews/brainx-review.md (deleted, previous review)
- PROGRESS.md
- src/personal_rag/api_client.py
- tests/harness.py
- tests/integration/test_api.py
- tests/integration/test_ui.py
- ui/app.py
