/** Conversation history list: new chat, switch, delete one, clear all. */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ROUTES } from '../../app/routes'
import { Button } from '../../components/Button'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { Icon } from '../../components/Icon'
import { formatRelative } from '../../lib/format'
import type { Conversation } from './types'
import styles from './ConversationSidebar.module.css'

interface ConversationSidebarProps {
  conversations: Conversation[]
  activeId: string | null
  pendingId: string | null
  persisted: boolean
  onNewChat: () => void
  onNavigate: () => void
  onDelete: (id: string) => void
  onClearAll: () => void
}

export function ConversationSidebar({
  conversations,
  activeId,
  pendingId,
  persisted,
  onNewChat,
  onNavigate,
  onDelete,
  onClearAll,
}: ConversationSidebarProps) {
  const [confirmClear, setConfirmClear] = useState(false)
  const [toDelete, setToDelete] = useState<Conversation | null>(null)

  return (
    <div className={styles.sidebar}>
      <div className={styles.top}>
        <Button variant="primary" icon="plus" onClick={onNewChat} className={styles.newChat}>
          New chat
        </Button>
      </div>

      <nav className={styles.list} aria-label="Conversation history">
        {conversations.length === 0 ? (
          <p className={styles.empty}>Your conversations will appear here.</p>
        ) : (
          <ul>
            {conversations.map((c) => (
              <li key={c.id} className={`${styles.item} ${c.id === activeId ? styles.active : ''}`}>
                <Link
                  to={ROUTES.conversation(c.id)}
                  className={styles.link}
                  aria-current={c.id === activeId ? 'page' : undefined}
                  onClick={onNavigate}
                >
                  <span className={styles.title}>{c.title}</span>
                  <span className={styles.time}>
                    {c.id === pendingId ? 'Answering…' : formatRelative(c.updatedAt)}
                  </span>
                </Link>
                <button
                  type="button"
                  className={styles.delete}
                  onClick={() => setToDelete(c)}
                  aria-label={`Delete conversation: ${c.title}`}
                  title="Delete conversation"
                >
                  <Icon name="trash" size={15} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </nav>

      <div className={styles.bottom}>
        <p className={styles.note}>
          <Icon name="info" size={13} />
          {persisted
            ? 'History is saved in this browser only.'
            : 'History can’t be saved in this browser and will be lost on reload.'}
        </p>
        {conversations.length > 0 && (
          <Button variant="ghost" size="sm" icon="trash" onClick={() => setConfirmClear(true)}>
            Clear history
          </Button>
        )}
      </div>

      <ConfirmDialog
        open={toDelete !== null}
        title="Delete this conversation?"
        confirmLabel="Delete"
        destructive
        onCancel={() => setToDelete(null)}
        onConfirm={() => {
          if (toDelete) onDelete(toDelete.id)
          setToDelete(null)
        }}
      >
        “{toDelete?.title}” will be removed from this browser. Your documents are not affected.
      </ConfirmDialog>

      <ConfirmDialog
        open={confirmClear}
        title="Clear all conversations?"
        confirmLabel="Clear history"
        destructive
        onCancel={() => setConfirmClear(false)}
        onConfirm={() => {
          onClearAll()
          setConfirmClear(false)
        }}
      >
        Every conversation saved in this browser will be removed. Your documents are not affected.
      </ConfirmDialog>
    </div>
  )
}
