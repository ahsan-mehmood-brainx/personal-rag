/**
 * A tiny in-memory stand-in for the backend, installed as `fetch`, for page-level unit tests.
 * Responses follow the real API's shapes. Full-stack behavior is covered by the Playwright
 * suite against the real FastAPI app.
 */
import { vi } from 'vitest'
import type { AskResponse, DocumentInfo } from '../api/types'

export interface FakeBackend {
  documents: DocumentInfo[]
  askResponse: AskResponse
  requests: Array<{ method: string; path: string; body?: unknown }>
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export function installFakeBackend(initial: Partial<FakeBackend> = {}): FakeBackend {
  const state: FakeBackend = {
    documents: initial.documents ?? [],
    askResponse: initial.askResponse ?? {
      status: 'answered',
      answer: 'An answer.',
      sources: [],
      web_sources: [],
      debug: null,
    },
    requests: [],
  }

  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = init.method ?? 'GET'
      const path = url.replace(/^\/api/, '')
      const body = typeof init.body === 'string' ? (JSON.parse(init.body) as unknown) : undefined
      state.requests.push({ method, path, body })

      if (path === '/health') {
        return json(200, {
          status: 'ok',
          documents: state.documents.length,
          chunks: 0,
          embedding_model: 'test-model',
          index_embedding_model: 'test-model',
          index_usable: true,
        })
      }
      if (path === '/documents' && method === 'GET') return json(200, state.documents)
      if (path.startsWith('/documents/') && method === 'DELETE') {
        const id = decodeURIComponent(path.slice('/documents/'.length))
        const before = state.documents.length
        state.documents = state.documents.filter((d) => d.doc_id !== id)
        return before === state.documents.length
          ? json(404, { detail: 'Document not found.' })
          : json(200, { deleted: id })
      }
      if (path === '/ask' && method === 'POST') return json(200, state.askResponse)
      return json(404, { detail: 'Not Found' })
    }),
  )
  return state
}
