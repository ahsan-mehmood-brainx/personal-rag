import type { ComponentPropsWithRef, ReactNode } from 'react'
import { Icon, type IconName } from './Icon'
import { Spinner } from './Spinner'
import styles from './Button.module.css'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md'

interface ButtonProps extends ComponentPropsWithRef<'button'> {
  variant?: Variant
  size?: Size
  icon?: IconName
  loading?: boolean
  /** Icon-only button. `aria-label` is then required for accessibility. */
  iconOnly?: boolean
  children?: ReactNode
}

export function Button({
  variant = 'secondary',
  size = 'md',
  icon,
  loading = false,
  iconOnly = false,
  className,
  children,
  disabled,
  type = 'button',
  ...rest
}: ButtonProps) {
  const classes = [
    styles.button,
    styles[variant],
    styles[size],
    iconOnly ? styles.iconOnly : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ')
  return (
    <button
      type={type}
      className={classes}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Spinner size={16} /> : icon ? <Icon name={icon} size={size === 'sm' ? 16 : 18} /> : null}
      {children}
    </button>
  )
}
