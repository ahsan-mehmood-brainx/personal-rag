/**
 * Documents page: upload, list and delete the files the assistant answers from.
 * All operations go through the backend (`/documents` endpoints); nothing is stored here.
 */
import { useCallback, useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import type { DocumentInfo, UploadResponse } from '../../api/types'
import { Button } from '../../components/Button'
import { Callout } from '../../components/Callout'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { useToast } from '../../components/Toast'
import { pluralize } from '../../lib/format'
import { useHealth } from '../health/HealthContext'
import { DocumentList } from './DocumentList'
import { UploadPanel } from './UploadPanel'
import { useDocuments } from './useDocuments'
import { useUploadQueue } from './useUploadQueue'
import styles from './DocumentsPage.module.css'

const UPLOAD_TOAST: Record<UploadResponse['status'], string> = {
  ingested: 'Document added',
  replaced: 'Document updated',
  duplicate: 'Already uploaded',
}

export function DocumentsPage() {
  const { documents, state, error, reload, remove } = useDocuments()
  const { status: apiStatus, health, refresh: refreshHealth } = useHealth()
  const { notify } = useToast()
  const inputRef = useRef<HTMLInputElement>(null)
  const [pendingDelete, setPendingDelete] = useState<DocumentInfo | null>(null)
  const [deleting, setDeleting] = useState(false)

  const onUploaded = useCallback(
    (result: UploadResponse) => {
      notify(
        result.status === 'duplicate' ? 'info' : 'success',
        UPLOAD_TOAST[result.status],
        result.filename,
      )
      void reload({ quiet: true })
      void refreshHealth()
    },
    [notify, reload, refreshHealth],
  )

  const onFailed = useCallback(
    (name: string, message: string) => notify('error', `Couldn't upload ${name}`, message),
    [notify],
  )

  const queue = useUploadQueue({ onUploaded, onFailed })

  const confirmDelete = async () => {
    if (!pendingDelete) return
    setDeleting(true)
    try {
      await remove(pendingDelete.doc_id)
      notify('success', 'Document deleted', pendingDelete.filename)
      setPendingDelete(null)
      void refreshHealth()
    } catch (err) {
      notify('error', 'Delete failed', err instanceof ApiError ? err.message : undefined)
    } finally {
      setDeleting(false)
    }
  }

  const indexUnusable = apiStatus === 'online' && health && !health.index_usable

  return (
    <div className={styles.page}>
      <div className={styles.inner}>
        <header className={styles.header}>
          <div>
            <h1>Documents</h1>
            <p className={styles.subtitle}>
              The assistant answers only from the files you add here.
            </p>
          </div>
          {state === 'ready' && documents.length > 0 && (
            <span className={styles.count} data-testid="document-count">
              {pluralize(documents.length, 'document')}
            </span>
          )}
        </header>

        {apiStatus === 'offline' && (
          <Callout
            tone="danger"
            title="Backend not reachable"
            role="alert"
            action={
              <Button size="sm" icon="refresh" onClick={() => void Promise.all([refreshHealth(), reload()])}>
                Retry
              </Button>
            }
          >
            Start the API (see the README), then retry. Uploads and deletes need it.
          </Callout>
        )}

        {indexUnusable && (
          <Callout tone="warning" title="The index needs rebuilding">
            It was built with a different embedding model ({health.index_embedding_model ?? 'unknown'}
            ) than the one configured ({health.embedding_model}). Run{' '}
            <code>uv run python -m personal_rag.cli reindex</code> and reload.
          </Callout>
        )}

        <UploadPanel
          inputRef={inputRef}
          items={queue.items}
          onFiles={queue.enqueue}
          onDismiss={queue.dismiss}
          onClearFinished={queue.clearFinished}
        />

        <section className={styles.listCard} aria-labelledby="documents-heading">
          <div className={styles.listHeader}>
            <h2 id="documents-heading">Your documents</h2>
            <Button
              variant="ghost"
              size="sm"
              icon="refresh"
              onClick={() => void reload()}
              disabled={state === 'loading'}
            >
              Refresh
            </Button>
          </div>
          <DocumentList
            documents={documents}
            state={state}
            error={error}
            onRetry={() => void reload()}
            onDelete={setPendingDelete}
            onUploadClick={() => inputRef.current?.click()}
          />
        </section>
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete this document?"
        confirmLabel="Delete"
        destructive
        busy={deleting}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setPendingDelete(null)}
      >
        <strong>{pendingDelete?.filename}</strong> and its {pluralize(pendingDelete?.chunk_count ?? 0, 'chunk')}{' '}
        will be removed from your knowledge base. The assistant will no longer answer from it.
      </ConfirmDialog>
    </div>
  )
}
