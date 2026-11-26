/**
 * Runtime configuration, read once from Vite env variables (see `web/.env.example`).
 *
 * Nothing here is secret: every `VITE_*` value ends up in the browser bundle. The limits are
 * client-side pre-checks for faster feedback; the backend enforces its own.
 */

function positiveInt(raw: string | undefined, fallback: number): number {
  const value = Number.parseInt(raw ?? '', 10)
  return Number.isFinite(value) && value > 0 ? value : fallback
}

function basePath(raw: string | undefined): string {
  const value = (raw ?? '').trim() || '/api'
  return value.endsWith('/') ? value.slice(0, -1) : value
}

export const config = {
  apiBaseUrl: basePath(import.meta.env.VITE_API_BASE_URL),
  maxUploadBytes: positiveInt(import.meta.env.VITE_MAX_UPLOAD_MB, 10) * 1024 * 1024,
  maxQuestionChars: positiveInt(import.meta.env.VITE_MAX_QUESTION_CHARS, 1000),
  /** Generous: an answer runs a classifier, an embedding and a generation call in sequence. */
  askTimeoutMs: 120_000,
  uploadTimeoutMs: 180_000,
  defaultTimeoutMs: 15_000,
} as const

/** File types the backend accepts (`ALLOWED_EXTENSIONS` in ingestion/validation.py). */
export const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.txt', '.md'] as const

/**
 * Capabilities the frontend can offer only when the backend supports them.
 *
 * externalSearch: the backend answers strictly from uploaded documents (`POST /ask` accepts
 * only `question` and `debug`, and the scope gate refuses anything needing outside
 * information). Until the backend exposes a flag for it, the UI shows the toggle locked OFF.
 * See web/README.md, "Missing backend APIs".
 */
export const capabilities = {
  externalSearch: false,
  serverConversationHistory: false,
} as const
