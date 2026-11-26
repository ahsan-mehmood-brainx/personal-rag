import { useState, type DragEvent, type RefObject } from 'react'
import { Button } from '../../components/Button'
import { Icon } from '../../components/Icon'
import { Spinner } from '../../components/Spinner'
import { ALLOWED_EXTENSIONS, config } from '../../config'
import { ACCEPT_ATTRIBUTE } from '../../lib/files'
import { formatBytes, pluralize } from '../../lib/format'
import type { UploadItem } from './useUploadQueue'
import styles from './UploadPanel.module.css'

interface UploadPanelProps {
  /** Owned by the page so other controls (the empty state) can open the file picker. */
  inputRef: RefObject<HTMLInputElement | null>
  items: UploadItem[]
  disabled?: boolean
  onFiles: (files: File[]) => void
  onDismiss: (id: string) => void
  onClearFinished: () => void
}

const TYPES_TEXT = ALLOWED_EXTENSIONS.map((e) => e.slice(1).toUpperCase()).join(', ')

function itemDetail(item: UploadItem): string {
  if (item.state === 'queued') return 'Waiting…'
  if (item.state === 'uploading') return 'Uploading and indexing…'
  if (item.state === 'failed') return item.error ?? 'Upload failed.'
  const result = item.result
  if (!result) return 'Done'
  if (result.status === 'duplicate') return 'Already in your knowledge base. Nothing changed.'
  if (result.status === 'replaced') {
    return `Replaced the earlier version · ${pluralize(result.chunk_count, 'chunk')}`
  }
  return `Indexed · ${pluralize(result.chunk_count, 'chunk')}`
}

export function UploadPanel({
  inputRef,
  items,
  disabled,
  onFiles,
  onDismiss,
  onClearFinished,
}: UploadPanelProps) {
  const [dragging, setDragging] = useState(false)
  const hasFinished = items.some((i) => i.state === 'done' || i.state === 'failed')

  const onDrop = (event: DragEvent) => {
    event.preventDefault()
    setDragging(false)
    if (disabled) return
    const files = Array.from(event.dataTransfer.files)
    if (files.length) onFiles(files)
  }

  return (
    <section className={styles.panel} aria-labelledby="upload-heading">
      <h2 id="upload-heading" className="visually-hidden">
        Upload documents
      </h2>
      <div
        className={`${styles.dropzone} ${dragging ? styles.dragging : ''} ${disabled ? styles.disabled : ''}`}
        onDragOver={(event) => {
          event.preventDefault()
          if (!disabled) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        data-testid="dropzone"
      >
        <span className={styles.dropIcon}>
          <Icon name="upload" size={22} />
        </span>
        <div className={styles.dropText}>
          <p className={styles.dropTitle}>
            Drag files here or{' '}
            <button
              type="button"
              className={styles.browse}
              onClick={() => inputRef.current?.click()}
              disabled={disabled}
            >
              browse
            </button>
          </p>
          <p className={styles.dropHint}>
            {TYPES_TEXT} · up to {formatBytes(config.maxUploadBytes)} each · multiple files allowed
          </p>
        </div>
        <Button
          variant="primary"
          icon="plus"
          className={styles.uploadButton}
          onClick={() => inputRef.current?.click()}
          disabled={disabled}
        >
          Upload
        </Button>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT_ATTRIBUTE}
          className="visually-hidden"
          tabIndex={-1}
          aria-label="Choose files to upload"
          data-testid="file-input"
          onChange={(event) => {
            const files = Array.from(event.target.files ?? [])
            event.target.value = '' // allow picking the same file again
            if (files.length) onFiles(files)
          }}
        />
      </div>

      {items.length > 0 && (
        <div className={styles.queue}>
          <div className={styles.queueHeader}>
            <span>Uploads</span>
            {hasFinished && (
              <button type="button" className={styles.clear} onClick={onClearFinished}>
                Clear finished
              </button>
            )}
          </div>
          <ul className={styles.items} aria-label="Upload progress">
            {items.map((item) => (
              <li key={item.id} className={`${styles.item} ${styles[item.state]}`}>
                <span className={styles.itemIcon} aria-hidden="true">
                  {item.state === 'uploading' || item.state === 'queued' ? (
                    <Spinner size={16} />
                  ) : (
                    <Icon name={item.state === 'done' ? 'check' : 'alert'} size={16} />
                  )}
                </span>
                <div className={styles.itemBody}>
                  <p className={styles.itemName}>{item.name}</p>
                  <p className={styles.itemDetail} role={item.state === 'failed' ? 'alert' : undefined}>
                    {itemDetail(item)}
                  </p>
                </div>
                <span className={styles.itemSize}>{formatBytes(item.size)}</span>
                {(item.state === 'done' || item.state === 'failed') && (
                  <button
                    type="button"
                    className={styles.dismiss}
                    onClick={() => onDismiss(item.id)}
                    aria-label={`Dismiss ${item.name}`}
                  >
                    <Icon name="close" size={14} />
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
