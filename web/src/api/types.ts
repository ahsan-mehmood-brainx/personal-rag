/**
 * Response and request shapes of the FastAPI backend.
 *
 * These mirror `src/personal_rag/schemas.py` and the models in `src/personal_rag/api/main.py`.
 * If the backend changes a model, change it here and in `guards.ts`.
 */

export type AskStatus = 'answered' | 'not_found' | 'out_of_scope' | 'meta' | 'no_documents' | 'error'

export const ASK_STATUSES: readonly AskStatus[] = [
  'answered',
  'not_found',
  'out_of_scope',
  'meta',
  'no_documents',
  'error',
]

export interface HealthResponse {
  status: string
  documents: number
  chunks: number
  embedding_model: string
  index_embedding_model: string | null
  index_usable: boolean
}

export interface DocumentInfo {
  doc_id: string
  filename: string
  chunk_count: number
  /** ISO 8601, UTC. */
  ingested_at: string
}

export type UploadStatus = 'ingested' | 'duplicate' | 'replaced'

export interface UploadResponse {
  doc_id: string
  filename: string
  status: UploadStatus
  chunk_count: number
}

export interface DeleteResponse {
  deleted: string
}

export interface AskRequest {
  question: string
  debug?: boolean
}

export interface Source {
  label: string
  filename: string
  section: string
  page: number | null
  similarity: number
  excerpt: string
}

export interface TokenUsage {
  input_tokens: number
  output_tokens: number
  reasoning_tokens: number
}

export interface DebugChunk {
  chunk_id: string
  filename: string
  section: string
  page: number | null
  similarity: number
  kept: boolean
}

export interface DebugInfo {
  classifier_category: string | null
  classifier_reason: string | null
  retrieved: DebugChunk[]
  threshold: number
  latency_ms: Record<string, number>
  token_usage: Record<string, TokenUsage>
}

export interface AskResponse {
  status: AskStatus
  answer: string
  sources: Source[]
  debug: DebugInfo | null
}
