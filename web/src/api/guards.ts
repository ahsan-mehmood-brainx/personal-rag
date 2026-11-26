/**
 * Runtime checks for backend responses.
 *
 * TypeScript types vanish at runtime, so a backend change or a proxy error page would otherwise
 * flow into components as `undefined` fields. Each guard checks the fields the UI reads.
 */
import {
  ASK_STATUSES,
  type AskResponse,
  type DeleteResponse,
  type DocumentInfo,
  type HealthResponse,
  type UploadResponse,
} from './types'

type Obj = Record<string, unknown>

function isObj(value: unknown): value is Obj {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

const isStr = (v: unknown): v is string => typeof v === 'string'
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const isPage = (v: unknown): boolean => v === null || isNum(v)

export function isHealthResponse(v: unknown): v is HealthResponse {
  return (
    isObj(v) &&
    isStr(v.status) &&
    isNum(v.documents) &&
    isNum(v.chunks) &&
    isStr(v.embedding_model) &&
    (v.index_embedding_model === null || isStr(v.index_embedding_model)) &&
    typeof v.index_usable === 'boolean'
  )
}

export function isDocumentInfo(v: unknown): v is DocumentInfo {
  return (
    isObj(v) && isStr(v.doc_id) && isStr(v.filename) && isNum(v.chunk_count) && isStr(v.ingested_at)
  )
}

export function isDocumentList(v: unknown): v is DocumentInfo[] {
  return Array.isArray(v) && v.every(isDocumentInfo)
}

export function isUploadResponse(v: unknown): v is UploadResponse {
  return (
    isObj(v) &&
    isStr(v.doc_id) &&
    isStr(v.filename) &&
    isNum(v.chunk_count) &&
    (v.status === 'ingested' || v.status === 'duplicate' || v.status === 'replaced')
  )
}

export function isDeleteResponse(v: unknown): v is DeleteResponse {
  return isObj(v) && isStr(v.deleted)
}

function isSource(v: unknown): boolean {
  return (
    isObj(v) &&
    isStr(v.label) &&
    isStr(v.filename) &&
    isStr(v.section) &&
    isPage(v.page) &&
    isNum(v.similarity) &&
    isStr(v.excerpt)
  )
}

function isDebugInfo(v: unknown): boolean {
  return (
    isObj(v) &&
    isNum(v.threshold) &&
    Array.isArray(v.retrieved) &&
    isObj(v.latency_ms) &&
    isObj(v.token_usage)
  )
}

export function isAskResponse(v: unknown): v is AskResponse {
  return (
    isObj(v) &&
    ASK_STATUSES.includes(v.status as AskResponse['status']) &&
    isStr(v.answer) &&
    (v.sources === undefined || (Array.isArray(v.sources) && v.sources.every(isSource))) &&
    (v.debug === undefined || v.debug === null || isDebugInfo(v.debug))
  )
}

/** Fill optional fields Pydantic may omit, so components never see `undefined`. */
export function normalizeAskResponse(v: AskResponse): AskResponse {
  return { ...v, sources: v.sources ?? [], debug: v.debug ?? null }
}
