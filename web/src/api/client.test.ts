import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, ask, deleteDocument, getHealth, listDocuments, uploadDocument } from './client'

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(body === undefined ? '' : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

function mockFetch(...responses: Array<Response | Error>) {
  const fn = vi.fn()
  for (const r of responses) {
    if (r instanceof Error) fn.mockRejectedValueOnce(r)
    else fn.mockResolvedValueOnce(r)
  }
  vi.stubGlobal('fetch', fn)
  return fn
}

async function caught(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise
  } catch (err) {
    if (err instanceof ApiError) return err
    throw err
  }
  throw new Error('expected an ApiError')
}

const answered = {
  status: 'answered',
  answer: 'You studied at Lakeview University.',
  sources: [
    { label: 'S1', filename: 'cv.md', section: 'Education', page: null, similarity: 0.71, excerpt: 'BSc…' },
  ],
  debug: null,
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api client', () => {
  it('lists documents through the /api base path', async () => {
    const docs = [{ doc_id: 'abc', filename: 'cv.md', chunk_count: 3, ingested_at: '2026-11-25T10:00:00Z' }]
    const fetchMock = mockFetch(jsonResponse(200, docs))
    await expect(listDocuments()).resolves.toEqual(docs)
    expect(fetchMock).toHaveBeenCalledWith('/api/documents', expect.objectContaining({ method: 'GET' }))
  })

  it('sends question and debug flag only, as the backend contract defines', async () => {
    const fetchMock = mockFetch(jsonResponse(200, answered))
    await ask({ question: 'Where did I study?', debug: true })
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(JSON.parse(init.body as string)).toEqual({ question: 'Where did I study?', debug: true })
  })

  it('returns the AskResponse body of an upstream 502 instead of throwing', async () => {
    const body = { status: 'error', answer: 'Something went wrong…', sources: [], debug: null }
    mockFetch(jsonResponse(502, body))
    await expect(ask({ question: 'q' })).resolves.toEqual(body)
  })

  it('fills sources and debug when the backend omits them', async () => {
    mockFetch(jsonResponse(200, { status: 'meta', answer: 'Hi' }))
    await expect(ask({ question: 'hello' })).resolves.toEqual({
      status: 'meta',
      answer: 'Hi',
      sources: [],
      debug: null,
    })
  })

  it('shows the backend detail message for HTTP errors', async () => {
    mockFetch(jsonResponse(415, { detail: 'Unsupported file type. Allowed: .pdf, .docx, .txt, .md.' }))
    const err = await caught(uploadDocument(new File(['x'], 'a.exe')))
    expect(err.kind).toBe('http')
    expect(err.status).toBe(415)
    expect(err.message).toBe('Unsupported file type. Allowed: .pdf, .docx, .txt, .md.')
  })

  it('posts uploads as multipart with the "file" field', async () => {
    const result = { doc_id: 'd1', filename: 'cv.md', status: 'ingested', chunk_count: 4 }
    const fetchMock = mockFetch(jsonResponse(200, result))
    await expect(uploadDocument(new File(['# CV'], 'cv.md'))).resolves.toEqual(result)
    const body = (fetchMock.mock.calls[0]?.[1] as RequestInit).body as FormData
    expect((body.get('file') as File).name).toBe('cv.md')
  })

  it('falls back to a status-based message when there is no detail', async () => {
    mockFetch(new Response('<html>oops</html>', { status: 413 }))
    const err = await caught(getHealth())
    expect(err.message).toBe('The file is larger than the upload limit.')
  })

  it('maps network failures and proxy errors to "unavailable"', async () => {
    mockFetch(new TypeError('Failed to fetch'))
    expect((await caught(getHealth())).kind).toBe('unavailable')

    mockFetch(jsonResponse(503, { detail: 'The backend API is not reachable.' }, { 'X-Proxy-Error': '1' }))
    const err = await caught(ask({ question: 'q' }))
    expect(err.kind).toBe('unavailable')
    expect(err.message).toMatch(/Cannot reach the backend API/)
  })

  it('rejects responses that do not match the expected shape', async () => {
    mockFetch(jsonResponse(200, [{ doc_id: 1 }]))
    expect((await caught(listDocuments())).kind).toBe('invalid_response')
  })

  it('reports a caller abort as "aborted"', async () => {
    const controller = new AbortController()
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
        }),
      ),
    )
    const pending = ask({ question: 'q' }, controller.signal)
    controller.abort()
    expect((await caught(pending)).kind).toBe('aborted')
  })

  it('encodes document ids in the delete path', async () => {
    const fetchMock = mockFetch(jsonResponse(200, { deleted: 'a/b' }))
    await deleteDocument('a/b')
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/documents/a%2Fb')
  })
})
