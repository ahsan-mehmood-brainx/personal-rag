/** Loads `GET /documents` and exposes loading / error / data plus `reload` and `remove`. */
import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, deleteDocument, listDocuments } from '../../api/client'
import type { DocumentInfo } from '../../api/types'

export type LoadState = 'loading' | 'ready' | 'error'

function newestFirst(a: DocumentInfo, b: DocumentInfo): number {
  return b.ingested_at.localeCompare(a.ingested_at) || a.filename.localeCompare(b.filename)
}

export function useDocuments() {
  const [documents, setDocuments] = useState<DocumentInfo[]>([])
  const [state, setState] = useState<LoadState>('loading')
  const [error, setError] = useState<string | null>(null)
  const controller = useRef<AbortController | null>(null)

  const reload = useCallback(async (options: { quiet?: boolean } = {}) => {
    controller.current?.abort()
    const current = new AbortController()
    controller.current = current
    // A quiet reload (after an upload or delete) keeps the list on screen instead of
    // flashing skeletons.
    if (!options.quiet) setState('loading')
    try {
      const list = await listDocuments(current.signal)
      setDocuments([...list].sort(newestFirst))
      setError(null)
      setState('ready')
    } catch (err) {
      if (err instanceof ApiError && err.kind === 'aborted') return
      setError(err instanceof ApiError ? err.message : 'Could not load documents.')
      setState('error')
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void reload(), 0)
    return () => {
      window.clearTimeout(timer)
      controller.current?.abort()
    }
  }, [reload])

  /** Delete on the server, then drop the row locally. Throws ApiError on failure. */
  const remove = useCallback(async (docId: string) => {
    try {
      await deleteDocument(docId)
    } catch (err) {
      // 404 means it is already gone (deleted elsewhere): treat as success for the list.
      if (!(err instanceof ApiError && err.status === 404)) throw err
    }
    setDocuments((current) => current.filter((d) => d.doc_id !== docId))
    // A list request started before the delete may still be in flight and would bring the row
    // back; reloading aborts it and shows the server's current state.
    void reload({ quiet: true })
  }, [reload])

  return { documents, state, error, reload, remove }
}
