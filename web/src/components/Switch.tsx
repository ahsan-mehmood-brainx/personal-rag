import { useId, type ReactNode } from 'react'
import styles from './Switch.module.css'

interface SwitchProps {
  checked: boolean
  onChange: (checked: boolean) => void
  label: ReactNode
  description?: ReactNode
  disabled?: boolean
  /** Extra content after the label, such as a status pill. */
  adornment?: ReactNode
  testId?: string
  /** Hide the label visually on narrow screens (it stays available to screen readers). */
  compact?: boolean
}

/** An accessible on/off switch (`role="switch"`), labelled and optionally described. */
export function Switch({
  checked,
  onChange,
  label,
  description,
  disabled = false,
  adornment,
  testId,
  compact = false,
}: SwitchProps) {
  const labelId = useId()
  const descriptionId = useId()
  return (
    <div
      className={`${styles.row} ${disabled ? styles.disabled : ''} ${compact ? styles.compact : ''}`}
    >
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={labelId}
        aria-describedby={description ? descriptionId : undefined}
        disabled={disabled}
        className={`${styles.track} ${checked ? styles.on : ''}`}
        onClick={() => onChange(!checked)}
        data-testid={testId}
      >
        <span className={styles.thumb} />
      </button>
      <div className={styles.text}>
        <span className={styles.labelLine}>
          <span id={labelId} className={styles.label}>
            {label}
          </span>
          {adornment}
        </span>
        {description && (
          <span id={descriptionId} className={styles.description}>
            {description}
          </span>
        )}
      </div>
    </div>
  )
}
