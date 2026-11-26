import type { DocumentInfo } from '../../api/types'
import { Badge } from '../../components/Badge'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { Icon } from '../../components/Icon'
import { Skeleton } from '../../components/Skeleton'
import { fileTypeLabel, formatDateTime, pluralize } from '../../lib/format'
import type { LoadState } from './useDocuments'
import styles from './DocumentList.module.css'

interface DocumentListProps {
  documents: DocumentInfo[]
  state: LoadState
  error: string | null
  onRetry: () => void
  onDelete: (doc: DocumentInfo) => void
  onUploadClick: () => void
}

function SkeletonRows() {
  return (
    <div className={styles.skeletons} aria-busy="true" aria-label="Loading documents">
      {[0, 1, 2].map((i) => (
        <div key={i} className={styles.skeletonRow}>
          <Skeleton width={32} height={32} radius={8} />
          <div className={styles.skeletonText}>
            <Skeleton width="45%" height={13} />
            <Skeleton width="25%" height={11} />
          </div>
          <Skeleton width={64} height={22} radius={999} />
        </div>
      ))}
    </div>
  )
}

export function DocumentList({ documents, state, error, onRetry, onDelete, onUploadClick }: DocumentListProps) {
  if (state === 'loading') return <SkeletonRows />

  if (state === 'error') {
    return (
      <EmptyState
        icon="alert"
        tone="danger"
        title="Couldn't load your documents"
        action={
          <Button icon="refresh" onClick={onRetry}>
            Try again
          </Button>
        }
      >
        {error}
      </EmptyState>
    )
  }

  if (documents.length === 0) {
    return (
      <EmptyState
        icon="book"
        title="No documents yet"
        action={
          <Button variant="primary" icon="upload" onClick={onUploadClick}>
            Upload your first document
          </Button>
        }
      >
        Upload your CV, project notes or certificates. The assistant answers only from what you add
        here.
      </EmptyState>
    )
  }

  return (
    <table className={styles.table}>
      <caption className="visually-hidden">Uploaded documents</caption>
      <thead>
        <tr>
          <th scope="col">Name</th>
          <th scope="col">Type</th>
          <th scope="col">Uploaded</th>
          <th scope="col">Status</th>
          <th scope="col">
            <span className="visually-hidden">Actions</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {documents.map((doc) => (
          <tr key={doc.doc_id} data-testid="document-row">
            <td className={styles.nameCell}>
              <span className={styles.fileIcon} aria-hidden="true">
                <Icon name="file" size={16} />
              </span>
              <span className={styles.fileName} title={doc.filename}>
                {doc.filename}
              </span>
            </td>
            <td className={styles.typeCell}>
              <span className={styles.mobileLabel}>Type</span>
              <Badge tone="neutral">{fileTypeLabel(doc.filename)}</Badge>
            </td>
            <td className={styles.dateCell}>
              <span className={styles.mobileLabel}>Uploaded</span>
              <time dateTime={doc.ingested_at}>{formatDateTime(doc.ingested_at)}</time>
            </td>
            <td className={styles.statusCell}>
              <span className={styles.mobileLabel}>Status</span>
              <Badge tone="success">
                <Icon name="check" size={12} />
                Indexed
              </Badge>
              <span className={styles.chunks}>{pluralize(doc.chunk_count, 'chunk')}</span>
            </td>
            <td className={styles.actionCell}>
              <Button
                variant="ghost"
                size="sm"
                iconOnly
                icon="trash"
                aria-label={`Delete ${doc.filename}`}
                title="Delete"
                onClick={() => onDelete(doc)}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
