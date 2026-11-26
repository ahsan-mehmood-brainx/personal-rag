/**
 * Upload queue: files are validated, then uploaded one at a time.
 *
 * Sequential on purpose: the backend serializes writes behind a lock, and one-at-a-time gives
 * the user a clear per-file status. The backend call is synchronous (it returns only after the
 * file is parsed, chunked and embedded), so "uploading" covers processing too.
 *
 * The queue keeps draining if the page unmounts (the user opens Chat mid-upload), so files the
 * user already chose are never silently dropped. Results still reach the app-wide toasts.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, uploadDocument } from '../../api/client'
import type { UploadResponse } from '../../api/types'
import { validateFile } from '../../lib/files'
import { newId } from '../../lib/storage'

export type UploadItemState = 'queued' | 'uploading' | 'done' | 'failed'

export interface UploadItem {
  id: string
  name: string
  size: number
  state: UploadItemState
  result?: UploadResponse
  error?: string
}

interface Options {
  /** Called after each successful upload, e.g. to refresh the document list. */
  onUploaded?: (result: UploadResponse) => void
  onFailed?: (name: string, message: string) => void
}

export function useUploadQueue({ onUploaded, onFailed }: Options = {}) {
  const [items, setItems] = useState<UploadItem[]>([])
  const files = useRef(new Map<string, File>())
  const running = useRef(false)
  const callbacks = useRef({ onUploaded, onFailed })

  useEffect(() => {
    callbacks.current = { onUploaded, onFailed }
  }, [onUploaded, onFailed])

  const update = useCallback((id: string, patch: Partial<UploadItem>) => {
    setItems((current) => current.map((item) => (item.id === id ? { ...item, ...patch } : item)))
  }, [])

  const drain = useCallback(async () => {
    if (running.current) return
    running.current = true
    try {
      for (const [id, file] of files.current) {
        files.current.delete(id)
        update(id, { state: 'uploading' })
        try {
          const result = await uploadDocument(file)
          update(id, { state: 'done', result })
          callbacks.current.onUploaded?.(result)
        } catch (err) {
          const message = err instanceof ApiError ? err.message : 'Upload failed.'
          update(id, { state: 'failed', error: message })
          callbacks.current.onFailed?.(file.name, message)
        }
      }
    } finally {
      running.current = false
    }
  }, [update])

  const enqueue = useCallback(
    (selected: Iterable<File>) => {
      const added: UploadItem[] = []
      for (const file of selected) {
        const id = newId()
        const problem = validateFile(file)
        if (problem) {
          added.push({ id, name: file.name, size: file.size, state: 'failed', error: problem })
        } else {
          files.current.set(id, file)
          added.push({ id, name: file.name, size: file.size, state: 'queued' })
        }
      }
      if (added.length === 0) return
      setItems((current) => [...added, ...current])
      void drain()
    },
    [drain],
  )

  const dismiss = useCallback((id: string) => {
    setItems((current) => current.filter((item) => item.id !== id))
  }, [])

  const clearFinished = useCallback(() => {
    setItems((current) => current.filter((i) => i.state === 'queued' || i.state === 'uploading'))
  }, [])

  const busy = items.some((i) => i.state === 'queued' || i.state === 'uploading')

  return { items, busy, enqueue, dismiss, clearFinished }
}
