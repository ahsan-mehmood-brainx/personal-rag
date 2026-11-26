import { Badge } from '../../components/Badge'
import { Button } from '../../components/Button'
import { Callout } from '../../components/Callout'
import { Icon } from '../../components/Icon'
import { AnswerText } from './AnswerText'
import { SourcesList, WebSourcesList } from './ResponseDetails'
import { STATUS_META } from './statusMeta'
import type { AssistantMessage, ChatMessage, FailedMessage } from './types'
import styles from './MessageItem.module.css'

function AssistantAvatar() {
  return (
    <span className={styles.avatar} aria-hidden="true">
      <Icon name="sparkle" size={16} />
    </span>
  )
}

/** Shown under an out-of-scope refusal when the question was sent with external search off. */
export function ExternalSearchNotice() {
  return (
    <div className={styles.notice} data-testid="external-search-notice">
      <Callout tone="neutral" icon="globe" title="External search is off">
        This question needs outside information, and answers currently come only from your uploaded
        documents. Turn on Allow External Search below and ask again to look it up on the web.
      </Callout>
    </div>
  )
}

function AssistantBubble({ message }: { message: AssistantMessage }) {
  const { response } = message
  const meta = STATUS_META[response.status]
  return (
    <article className={`${styles.row} ${styles.assistantRow}`} aria-label={`Assistant: ${meta.label}`}>
      <AssistantAvatar />
      <div className={`${styles.bubble} ${styles.assistant}`} data-status={response.status}>
        <div className={styles.badgeRow}>
          <Badge tone={meta.tone}>{meta.label}</Badge>
        </div>
        <AnswerText text={response.answer} />
        {response.status === 'out_of_scope' && !message.externalSearch && <ExternalSearchNotice />}
        <SourcesList sources={response.sources} />
        <WebSourcesList sources={response.web_sources} />
      </div>
    </article>
  )
}

function FailedBubble({
  message,
  onRetry,
  retryDisabled,
}: {
  message: FailedMessage
  onRetry: () => void
  retryDisabled: boolean
}) {
  return (
    <article className={`${styles.row} ${styles.assistantRow}`} aria-label="Request failed">
      <AssistantAvatar />
      <div className={`${styles.bubble} ${styles.failed}`} role="alert">
        <div className={styles.failedHead}>
          <Icon name="alert" size={16} />
          <span>{message.text}</span>
        </div>
        <Button size="sm" icon="refresh" onClick={onRetry} disabled={retryDisabled}>
          Retry
        </Button>
      </div>
    </article>
  )
}

interface MessageItemProps {
  message: ChatMessage
  onRetry: (messageId: string) => void
  busy: boolean
}

export function MessageItem({ message, onRetry, busy }: MessageItemProps) {
  if (message.role === 'user') {
    return (
      <article className={`${styles.row} ${styles.userRow}`} aria-label="You">
        <div className={`${styles.bubble} ${styles.user}`}>{message.text}</div>
      </article>
    )
  }
  if (message.role === 'failure') {
    return <FailedBubble message={message} onRetry={() => onRetry(message.id)} retryDisabled={busy} />
  }
  return <AssistantBubble message={message} />
}

export function PendingMessage({ onStop, externalSearch }: { onStop: () => void; externalSearch: boolean }) {
  return (
    <div className={`${styles.row} ${styles.assistantRow}`} data-testid="pending-message">
      <AssistantAvatar />
      <div className={`${styles.bubble} ${styles.assistant} ${styles.pending}`}>
        <span className={styles.dots} aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
        <span role="status">
          {externalSearch ? 'Searching your documents and the web…' : 'Searching your documents…'}
        </span>
        <Button size="sm" variant="ghost" icon="stop" onClick={onStop} className={styles.stop}>
          Stop
        </Button>
      </div>
    </div>
  )
}
