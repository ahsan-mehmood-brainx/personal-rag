import type { ReactNode } from 'react'
import { Icon, type IconName } from './Icon'
import styles from './EmptyState.module.css'

interface EmptyStateProps {
  icon: IconName
  title: string
  children?: ReactNode
  action?: ReactNode
  tone?: 'default' | 'danger'
}

export function EmptyState({ icon, title, children, action, tone = 'default' }: EmptyStateProps) {
  return (
    <div className={`${styles.empty} ${tone === 'danger' ? styles.danger : ''}`}>
      <span className={styles.iconWrap}>
        <Icon name={icon} size={22} />
      </span>
      <h2 className={styles.title}>{title}</h2>
      {children && <div className={styles.text}>{children}</div>}
      {action && <div className={styles.action}>{action}</div>}
    </div>
  )
}
