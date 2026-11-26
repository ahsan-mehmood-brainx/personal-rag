import type { ReactNode } from 'react'
import { Icon, type IconName } from './Icon'
import styles from './Callout.module.css'

type CalloutTone = 'info' | 'warning' | 'danger' | 'neutral'

const ICONS: Record<CalloutTone, IconName> = {
  info: 'info',
  warning: 'alert',
  danger: 'alert',
  neutral: 'info',
}

interface CalloutProps {
  tone?: CalloutTone
  title?: string
  icon?: IconName
  action?: ReactNode
  children?: ReactNode
  /** `alert` interrupts screen readers; use it only for errors the user must notice now. */
  role?: 'alert' | 'status' | 'note'
}

export function Callout({ tone = 'info', title, icon, action, children, role = 'note' }: CalloutProps) {
  return (
    <div className={`${styles.callout} ${styles[tone]}`} role={role}>
      <Icon name={icon ?? ICONS[tone]} size={18} className={styles.icon} />
      <div className={styles.body}>
        {title && <p className={styles.title}>{title}</p>}
        {children && <div className={styles.text}>{children}</div>}
      </div>
      {action && <div className={styles.action}>{action}</div>}
    </div>
  )
}
