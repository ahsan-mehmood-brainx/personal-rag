# Personal RAG Assistant: web frontend

A React + TypeScript single-page app for the Personal RAG Assistant. It manages documents and
runs the chat, and talks only to the FastAPI backend in this repository. It holds no secrets
and has no business logic: scope decisions, retrieval and refusals all happen in the backend.

The Streamlit UI in `ui/` still works and is unchanged.

## Run it locally

Requirements: Node.js 20.19 or newer, plus the backend set up as described in the root README.

```bash
# Terminal 1, from the repository root: the API
uv run uvicorn personal_rag.api.main:app --host 127.0.0.1 --port 8000

# Terminal 2: the frontend
cd web
npm install
npm run dev
```

Open <http://127.0.0.1:5173>. The dev server forwards `/api/*` to the backend, so the backend
needs no CORS setup and stays bound to `127.0.0.1`.

Production build: `npm run build`, then `npm run preview` (serves `dist/` on port 4173 with the
same `/api` proxy).

### Configuration

Optional. Copy `web/.env.example` to `web/.env.local` to override:

| Variable | Default | Meaning |
|---|---|---|
| `API_PROXY_TARGET` | `http://127.0.0.1:8000` | Backend the dev/preview server proxies `/api` to |
| `VITE_API_BASE_URL` | `/api` | Base path the browser calls |
| `VITE_MAX_UPLOAD_MB` | `10` | Client pre-check; keep in step with the backend's `MAX_UPLOAD_MB` |
| `VITE_MAX_QUESTION_CHARS` | `1000` | Client pre-check; keep in step with `MAX_QUESTION_CHARS` |

Every `VITE_*` value is bundled into browser code. Never put an API key in these files.

## Checks

```bash
npm run lint        # ESLint
npm run typecheck   # TypeScript, strict mode
npm test            # Vitest unit and component tests (jsdom, no backend needed)
npm run e2e         # Playwright end-to-end tests (see below)
npm run check       # lint + typecheck + unit tests
```

The end-to-end tests start two servers themselves: `e2e/fake_api_server.py` (the real FastAPI
app with real validation, parsing, chunking and ChromaDB, but the backend's fake embedder and
LLMs and a temporary data directory) and Vite on port 5174. They need `uv` and the backend's
Python environment, make no OpenAI calls, and never touch `data/`. The first run needs
`npx playwright install chromium`. Tests run at desktop (1366px), tablet (820px) and mobile
(390px) widths.

## Features

**Documents** (`/documents`)
- Upload PDF, DOCX, TXT and MD files by drag and drop or file picker, several at once. Files
  upload one at a time with per-file status: waiting, uploading and indexing, indexed,
  already uploaded, replaced, or failed with the reason.
- Client pre-checks for type, size and empty files; legacy `.doc` gets a "save as .docx" hint.
  The backend's own validation messages (415, 422, 413) are shown verbatim.
- A list with name, type, upload date, status and chunk count, newest first. It becomes stacked
  cards on narrow screens.
- Delete with a confirmation dialog. Loading skeletons, an empty state, an error state with
  retry, and toasts.
- Banners when the API is offline or the index needs `reindex`.

**Chat** (`/chat`, `/chat/:id`)
- Text input only. There are no attachments, images, voice or audio controls.
- Every backend status has its own badge: Answered, Not in your documents, Out of scope, Info,
  No documents, Error. Answers render paragraphs, lists and bold safely (no `innerHTML`), with
  expandable sources: label, file, section, page, similarity and excerpt.
- A loading indicator with Stop; failed requests can be retried without retyping.
- "Show internals" sends `debug: true` and shows the classifier decision, retrieved chunks
  against the threshold, latency and token use.
- Conversation history sidebar (a drawer on tablet and phone): new chat, switch, delete,
  clear all.
- **Allow External Search** toggle, visible under the input and OFF by default. See the next
  section for why it is locked.

**General**: light, dark and system themes; a backend health indicator; keyboard and
screen-reader support (labelled controls, live regions, focus-trapped dialogs, skip link);
reduced-motion support.

## Missing backend APIs

These parts of the frontend brief have no backend support. Following the brief, the frontend
does not invent endpoints or fake the behavior.

1. **External search.** `POST /ask` accepts only `question` and `debug`. The backend answers
   strictly from uploaded documents, and its scope gate is designed to refuse anything that
   needs outside information (spec section 2.1). The toggle is therefore shown locked OFF with
   an explanation. When a question is refused as out of scope, the answer carries an "External
   search is off" notice. The toggle value is **not** sent to `/ask`: Pydantic would silently
   ignore an unknown field, which would look like it works when it does not.
   *Needed to enable it:* an `/ask` request field (for example `allow_external_search: bool`),
   a backend search provider, and a scope policy decision. Then set
   `capabilities.externalSearch = true` in `src/config.ts` and include the field in `ask()` in
   `src/api/client.ts`.
2. **Server-side conversation history.** The backend is stateless and stores no chats, so
   history is kept in this browser's `localStorage` (key `prag.conversations.v1`, at most 50
   conversations). It does not follow you to another browser, and "Clear history" removes it.
   Each question is still answered on its own; earlier turns are not sent as context.
3. **Asynchronous processing status.** `POST /documents` is synchronous: it returns once
   parsing, chunking and embedding finish. Every listed document is therefore "Indexed"; the
   upload queue shows "Uploading and indexing…" while a file is processed. A real progress
   percentage would need a job or status endpoint.
4. **Legacy `.doc` files** are not accepted by the backend (`ALLOWED_EXTENSIONS`). The UI
   explains this instead of uploading them.
5. **Authentication.** The backend has none (single-user, localhost-only), so the frontend has
   none either. Add both together if the app is ever exposed beyond `127.0.0.1`.

## Structure

```
web/
├── index.html               # applies the saved theme before first paint
├── vite.config.ts           # dev/preview /api proxy, Vitest config
├── playwright.config.ts     # e2e: starts the fake API and Vite, 3 viewports
├── e2e/
│   ├── fake_api_server.py   # real FastAPI app + fake LLMs + temp data dir
│   ├── helpers.ts
│   ├── documents.spec.ts
│   └── chat.spec.ts
└── src/
    ├── main.tsx, config.ts  # entry; env config and capability flags
    ├── api/                 # the only HTTP code: client.ts, types.ts, guards.ts
    ├── app/                 # App (providers + routes), AppShell, theme
    ├── components/          # design-system pieces: Button, Badge, Switch, Callout,
    │                        # ConfirmDialog, Toast, Skeleton, EmptyState, Icon, Spinner
    ├── features/
    │   ├── documents/       # page, upload panel + queue, list, data hook
    │   ├── chat/            # page, provider, composer, messages, sidebar, toggle, store
    │   └── health/          # /health polling context + header indicator
    ├── lib/                 # formatting, file checks, safe localStorage
    ├── styles/              # tokens.css (light/dark), global.css
    └── test/                # Vitest setup, in-memory fetch stub, render helper
```

Styling uses CSS Modules over design tokens in `src/styles/tokens.css`; there is no UI framework.
Runtime dependencies are `react`, `react-dom` and `react-router-dom`.
