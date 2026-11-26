---
diff_hash: 5f417a228a0d1c193d96ec94917c40eaa00c790ef7e057626393eac05645f725
reviewed_at: 2026-11-26T06:36:04Z
---

## Summary

Adds the React 19 + Vite + TypeScript web frontend in `web/` (documents page, chat with browser-side history, health indicator, light/dark themes, unit and Playwright e2e tests) and a README pointer to it. Stack: React (Context for shared state, CSS Modules, no Redux in this project). All requests go through one typed client with runtime response guards, answers render as React elements (no innerHTML), no secrets in the bundle, `.env.example` is present. Lint, typecheck and 37 unit tests pass. Three findings were raised and fixed in the same pass; no Critical or High issues.

## Findings

### Critical (0)

### High (0)

### Medium (1)
- **web/src/features/documents/useUploadQueue.ts:53-70** — The queue stopped draining when the Documents page unmounted, so files still waiting were silently dropped if the user switched to Chat mid-upload. *(correctness)*
  - status: fixed
  - dev_reasoning: N/A
  - ai_reasoning: Removed the unmount guard so the queue finishes every chosen file. Results still reach the app-level toast provider, and state updates after unmount are harmless in React 19.

### Low (2)
- **web/src/features/documents/useDocuments.ts:46-54** — A list request already in flight when a delete completes could resolve afterwards and bring the deleted row back. *(correctness)*
  - status: fixed
  - dev_reasoning: N/A
  - ai_reasoning: After a successful delete the hook now runs a quiet reload, which aborts the stale request and shows the server's current list.
- **web/src/app/App.tsx:17** — Route paths (`/chat`, `/documents`, `/chat/:id`) were repeated as string literals across App, AppShell, ChatPage and ConversationSidebar. *(maintainability)*
  - status: fixed
  - dev_reasoning: N/A
  - ai_reasoning: Added web/src/app/routes.ts with a ROUTES constant and replaced the literals in those four files.

## Reviewed files
- README.md
- web/ (90 source, config, test and e2e files; node_modules, dist and test-results are gitignored and were not reviewed)
- web/src/app/routes.ts (added during this review)
