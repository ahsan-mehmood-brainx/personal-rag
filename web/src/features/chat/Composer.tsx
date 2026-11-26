/**
 * Text-only message composer. No attachments, voice or media input, by design.
 * Enter sends, Shift+Enter adds a line. The length limit mirrors the backend's
 * MAX_QUESTION_CHARS; the backend still enforces its own.
 */
import { useLayoutEffect, useRef, type FormEvent, type KeyboardEvent, type ReactNode } from 'react'
import { Button } from '../../components/Button'
import { config } from '../../config'
import styles from './Composer.module.css'

interface ComposerProps {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  busy: boolean
  toolbar?: ReactNode
  autoFocus?: boolean
}

const MAX_HEIGHT = 200

export function Composer({ value, onChange, onSubmit, busy, toolbar, autoFocus }: ComposerProps) {
  const ref = useRef<HTMLTextAreaElement>(null)
  const max = config.maxQuestionChars
  const length = value.trim().length
  const tooLong = value.length > max
  const canSend = length > 0 && !tooLong && !busy
  const showCount = value.length >= max * 0.8

  // Grow with the content up to a cap, then scroll.
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`
  }, [value])

  const submit = (event?: FormEvent) => {
    event?.preventDefault()
    if (canSend) onSubmit()
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // isComposing: do not send while an IME (e.g. Japanese, Chinese input) is mid-composition.
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form className={styles.composer} onSubmit={submit} aria-label="Ask a question">
      <div className={`${styles.field} ${tooLong ? styles.invalid : ''}`}>
        <label htmlFor="question" className="visually-hidden">
          Your question
        </label>
        <textarea
          id="question"
          ref={ref}
          rows={1}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask about your experience, skills, projects…"
          className={styles.input}
          autoFocus={autoFocus}
          aria-invalid={tooLong || undefined}
          aria-describedby={tooLong ? 'question-error' : undefined}
          enterKeyHint="send"
          autoComplete="off"
        />
        <Button
          type="submit"
          variant="primary"
          iconOnly
          icon="send"
          aria-label="Send"
          disabled={!canSend}
          className={styles.send}
        />
      </div>
      <div className={styles.footer}>
        <div className={styles.toolbar}>{toolbar}</div>
        <div className={styles.meta}>
          {tooLong ? (
            <span id="question-error" className={styles.error} role="alert">
              {value.length - max} characters over the {max} limit
            </span>
          ) : showCount ? (
            <span className={styles.count}>
              {value.length}/{max}
            </span>
          ) : (
            <span className={styles.hint}>Enter to send · Shift+Enter for a new line</span>
          )}
        </div>
      </div>
    </form>
  )
}
