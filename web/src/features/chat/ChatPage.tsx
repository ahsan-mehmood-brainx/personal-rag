/**
 * Chat page: conversation history, message thread, composer and chat toggles.
 * Each question goes to `POST /ask`; history is kept in this browser (the backend is stateless).
 */
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ROUTES } from '../../app/routes'
import { Button } from '../../components/Button'
import { Callout } from '../../components/Callout'
import { Icon } from '../../components/Icon'
import { Switch } from '../../components/Switch'
import { capabilities } from '../../config'
import { useHealth } from '../health/HealthContext'
import { useChat } from './ChatContext'
import { Composer } from './Composer'
import { ConversationSidebar } from './ConversationSidebar'
import { ExternalSearchToggle } from './ExternalSearchToggle'
import { MessageItem, PendingMessage } from './MessageItem'
import styles from './ChatPage.module.css'

const SUGGESTIONS = [
  'Summarize my professional experience',
  'What are my strongest technical skills?',
  'Which projects have I worked on?',
  'What can you do?',
]

function Welcome({ onPick, disabled }: { onPick: (q: string) => void; disabled: boolean }) {
  const { status, health } = useHealth()
  const noDocuments = status === 'online' && health?.documents === 0
  return (
    <div className={styles.welcome}>
      <span className={styles.welcomeIcon} aria-hidden="true">
        <Icon name="sparkle" size={24} />
      </span>
      <h1 className={styles.welcomeTitle}>Ask about your background</h1>
      <p className={styles.welcomeText}>
        Answers come only from the documents you upload, with the sources they came from.
      </p>
      {noDocuments && (
        <div className={styles.welcomeCallout}>
          <Callout
            tone="warning"
            title="No documents yet"
            action={
              <Link to={ROUTES.documents} className={styles.calloutLink}>
                Upload documents
              </Link>
            }
          >
            Upload your CV or other personal documents first, so there is something to answer from.
          </Callout>
        </div>
      )}
      <div className={styles.suggestions} aria-label="Suggested questions">
        {SUGGESTIONS.map((q) => (
          <button
            key={q}
            type="button"
            className={styles.suggestion}
            onClick={() => onPick(q)}
            disabled={disabled}
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  )
}

export function ChatPage() {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const chat = useChat()
  const { status: apiStatus } = useHealth()
  const [draft, setDraft] = useState('')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  const active = conversationId ? chat.conversations.find((c) => c.id === conversationId) : undefined
  const activeId = active?.id ?? null
  const busy = chat.pending !== null
  const pendingHere = chat.pending !== null && chat.pending.conversationId === activeId

  // Unknown id in the URL (deleted, or from another browser): fall back to a new chat.
  useEffect(() => {
    if (conversationId && !active) navigate(ROUTES.chat, { replace: true })
  }, [conversationId, active, navigate])

  const messageCount = active?.messages.length ?? 0
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: 'end', behavior: 'smooth' })
  }, [messageCount, pendingHere, activeId])

  useEffect(() => {
    if (!drawerOpen) return
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && setDrawerOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [drawerOpen])

  const ask = (question: string) => {
    const id = chat.send(activeId, question)
    if (!id) return
    setDraft('')
    if (id !== activeId) navigate(ROUTES.conversation(id), { replace: !conversationId })
  }

  const newChat = () => {
    setDrawerOpen(false)
    setDraft('')
    navigate(ROUTES.chat)
  }

  return (
    <div className={styles.page}>
      <aside
        className={`${styles.sidebar} ${drawerOpen ? styles.sidebarOpen : ''}`}
        aria-label="Chat history"
        data-testid="chat-sidebar"
      >
        <div className={styles.drawerHead}>
          <span>History</span>
          <Button
            variant="ghost"
            size="sm"
            iconOnly
            icon="close"
            aria-label="Close history"
            onClick={() => setDrawerOpen(false)}
          />
        </div>
        <ConversationSidebar
          conversations={chat.conversations}
          activeId={activeId}
          pendingId={chat.pending?.conversationId ?? null}
          persisted={chat.persisted}
          onNewChat={newChat}
          onNavigate={() => setDrawerOpen(false)}
          onDelete={(id) => {
            chat.deleteConversation(id)
            if (id === activeId) navigate(ROUTES.chat, { replace: true })
          }}
          onClearAll={() => {
            chat.clearAll()
            navigate(ROUTES.chat, { replace: true })
          }}
        />
      </aside>
      {drawerOpen && <div className={styles.scrim} onClick={() => setDrawerOpen(false)} aria-hidden="true" />}

      <section className={styles.main} aria-label="Chat">
        <header className={styles.chatHeader}>
          <Button
            variant="ghost"
            size="sm"
            iconOnly
            icon="history"
            aria-label="Open history"
            className={styles.historyButton}
            onClick={() => setDrawerOpen(true)}
          />
          <h2 className={styles.chatTitle}>{active?.title ?? 'New chat'}</h2>
          <div className={styles.headerTools}>
            <Switch
              checked={chat.showInternals}
              onChange={chat.setShowInternals}
              label="Show internals"
              testId="internals-toggle"
              compact
            />
            <Button
              variant="ghost"
              size="sm"
              iconOnly
              icon="plus"
              aria-label="New chat"
              className={styles.headerNewChat}
              onClick={newChat}
            />
          </div>
        </header>

        <div className={styles.scroll}>
          <div className={styles.thread} role="log" aria-label="Messages" aria-live="polite">
            {!active || active.messages.length === 0 ? (
              <Welcome onPick={ask} disabled={busy} />
            ) : (
              active.messages.map((message) => (
                <MessageItem
                  key={message.id}
                  message={message}
                  busy={busy}
                  onRetry={(messageId) => chat.retry(active.id, messageId)}
                />
              ))
            )}
            {pendingHere && <PendingMessage onStop={chat.stop} />}
            <div ref={endRef} />
          </div>
        </div>

        <div className={styles.composerWrap}>
          <div className={styles.composerInner}>
            {apiStatus === 'offline' && (
              <div className={styles.offline}>
                <Callout tone="danger" role="alert" title="Backend not reachable">
                  Questions can&apos;t be answered until the API is running.
                </Callout>
              </div>
            )}
            {busy && !pendingHere && (
              <p className={styles.busyElsewhere} role="status">
                Another conversation is still waiting for an answer.
              </p>
            )}
            <Composer
              value={draft}
              onChange={setDraft}
              onSubmit={() => ask(draft)}
              busy={busy}
              autoFocus
              toolbar={
                <ExternalSearchToggle
                  checked={chat.externalSearch}
                  available={capabilities.externalSearch}
                  onChange={chat.setExternalSearch}
                />
              }
            />
          </div>
        </div>
      </section>
    </div>
  )
}
