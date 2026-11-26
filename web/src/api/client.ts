/**
 * The single place the app talks HTTP to the backend.
 *
 * Every endpoint function returns a validated value or throws `ApiError` with a message that
 * is safe to show the user. Backend error bodies are `{"detail": "..."}` with fixed,
 * value-free text (see api/main.py), so `detail` is shown as-is.
 */
import { config } from '../config'
import {
  isAskResponse,
  isDeleteResponse,
  isDocumentList,
  isHealthResponse,
  isUploadResponse,
  normalizeAskResponse,
} from './guards'
import type {
  AskRequest,
  AskResponse,
  DeleteResponse,
  DocumentInfo,
  HealthResponse,
  UploadResponse,
} from './types'

export type ApiErrorKind = 'unavailable' | 'timeout' | 'http' | 'invalid_response' | 'aborted'

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | null

  constructor(kind: ApiErrorKind, message: string, status: number | null = null) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
  }
}

const UNAVAILABLE_MESSAGE =
  'Cannot reach the backend API. Check that it is running, then try again.'

const FALLBACK_BY_STATUS: Record<number, string> = {
  400: 'The request was not valid.',
  404: 'Not found.',
  413: 'The file is larger than the upload limit.',
  415: 'This file type is not supported.',
  422: 'The file could not be read.',
  502: 'The language model service failed. Please try again.',
  503: 'The backend is not ready.',
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'DELETE'
  body?: BodyInit
  json?: unknown
  timeoutMs?: number
  signal?: AbortSignal
}

interface RawResponse {
  status: number
  ok: boolean
  body: unknown
  proxyError: boolean
}

async function readBody(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text) as unknown
  } catch {
    return undefined // not JSON: an HTML error page or similar
  }
}

function detailOf(body: unknown): string | null {
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string' && detail.trim()) return detail
  }
  return null
}

async function send(path: string, options: RequestOptions = {}): Promise<RawResponse> {
  const timeout = new AbortController()
  const timer = setTimeout(() => timeout.abort(), options.timeoutMs ?? config.defaultTimeoutMs)
  const signal = options.signal
    ? AbortSignal.any([options.signal, timeout.signal])
    : timeout.signal

  const headers: Record<string, string> = { Accept: 'application/json' }
  let body = options.body
  if (options.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.json)
  }

  try {
    const response = await fetch(`${config.apiBaseUrl}${path}`, {
      method: options.method ?? 'GET',
      headers,
      body,
      signal,
    })
    return {
      status: response.status,
      ok: response.ok,
      body: await readBody(response),
      proxyError: response.headers.get('X-Proxy-Error') === '1',
    }
  } catch {
    if (options.signal?.aborted) throw new ApiError('aborted', 'Request cancelled.')
    if (timeout.signal.aborted) {
      throw new ApiError('timeout', 'The backend took too long to respond. Please try again.')
    }
    // fetch rejects with TypeError on network failure (backend down, DNS, CORS).
    throw new ApiError('unavailable', UNAVAILABLE_MESSAGE)
  } finally {
    clearTimeout(timer)
  }
}

function toHttpError(raw: RawResponse): ApiError {
  if (raw.proxyError) return new ApiError('unavailable', UNAVAILABLE_MESSAGE, raw.status)
  const message =
    detailOf(raw.body) ??
    FALLBACK_BY_STATUS[raw.status] ??
    `The backend returned an unexpected error (HTTP ${raw.status}).`
  return new ApiError('http', message, raw.status)
}

function expect<T>(raw: RawResponse, guard: (v: unknown) => v is T): T {
  if (!raw.ok) throw toHttpError(raw)
  if (!guard(raw.body)) {
    throw new ApiError(
      'invalid_response',
      'The backend sent a response this app does not understand.',
      raw.status,
    )
  }
  return raw.body
}

// --- endpoints -----------------------------------------------------------------------------

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return expect(await send('/health', { signal }), isHealthResponse)
}

export async function listDocuments(signal?: AbortSignal): Promise<DocumentInfo[]> {
  return expect(await send('/documents', { signal }), isDocumentList)
}

export async function uploadDocument(file: File, signal?: AbortSignal): Promise<UploadResponse> {
  const form = new FormData()
  form.append('file', file, file.name)
  const raw = await send('/documents', {
    method: 'POST',
    body: form,
    timeoutMs: config.uploadTimeoutMs,
    signal,
  })
  return expect(raw, isUploadResponse)
}

export async function deleteDocument(docId: string): Promise<DeleteResponse> {
  return expect(
    await send(`/documents/${encodeURIComponent(docId)}`, { method: 'DELETE' }),
    isDeleteResponse,
  )
}

/**
 * Ask one question. An upstream model failure is HTTP 502 but its body is still a normal
 * `AskResponse` with status `error` and a fixed message, so it is returned, not thrown.
 */
export async function ask(request: AskRequest, signal?: AbortSignal): Promise<AskResponse> {
  const raw = await send('/ask', {
    method: 'POST',
    json: {
      question: request.question,
      debug: request.debug ?? false,
      allow_external_search: request.allow_external_search ?? false,
    },
    timeoutMs: config.askTimeoutMs,
    signal,
  })
  if (raw.status === 502 && !raw.proxyError && isAskResponse(raw.body)) {
    return normalizeAskResponse(raw.body)
  }
  return normalizeAskResponse(expect(raw, isAskResponse))
}
