import { useHealth } from './HealthContext'
import styles from './HealthIndicator.module.css'

/** Compact status pill for the header: API reachable, offline, or index needs a reindex. */
export function HealthIndicator() {
  const { status, health } = useHealth()

  let tone = 'loading'
  let label = 'Connecting…'
  let title = 'Checking the backend API'
  if (status === 'offline') {
    tone = 'offline'
    label = 'Offline'
    title = 'The backend API is not reachable'
  } else if (status === 'online' && health && !health.index_usable) {
    tone = 'warning'
    label = 'Reindex needed'
    title = 'The index was built with a different embedding model'
  } else if (status === 'online') {
    tone = 'online'
    label = 'Connected'
    title = `Backend online · embedding model ${health?.embedding_model ?? 'unknown'}`
  }

  return (
    <span className={`${styles.pill} ${styles[tone]}`} title={title} data-testid="health-indicator">
      <span className={styles.dot} aria-hidden="true" />
      <span className={styles.label}>{label}</span>
    </span>
  )
}
