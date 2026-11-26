/**
 * Toast notifications: short-lived confirmations and errors for background actions.
 *
 * The region is an `aria-live` area, so screen readers announce new toasts. Errors stay
 * longer than successes because they usually need reading.
 */
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import { Icon, type IconName } from './Icon'
import styles from './Toast.module.css'

type ToastTone = 'success' | 'error' | 'info'

interface Toast {
  id: number
  tone: ToastTone
  title: string
  message?: string
}

interface ToastApi {
  notify: (tone: ToastTone, title: string, message?: string) => void
}

const ToastContext = createContext<ToastApi | null>(null)

const ICONS: Record<ToastTone, IconName> = { success: 'check', error: 'alert', info: 'info' }
const DURATION_MS: Record<ToastTone, number> = { success: 4000, info: 5000, error: 8000 }

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(1)

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((t) => t.id !== id))
  }, [])

  const notify = useCallback(
    (tone: ToastTone, title: string, message?: string) => {
      const id = nextId.current++
      // Keep the stack short so a burst (multi-file upload) does not cover the page.
      setToasts((current) => [...current.slice(-3), { id, tone, title, message }])
      window.setTimeout(() => dismiss(id), DURATION_MS[tone])
    },
    [dismiss],
  )

  const api = useMemo(() => ({ notify }), [notify])

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className={styles.region} aria-live="polite" aria-relevant="additions">
        {toasts.map((toast) => (
          <div key={toast.id} className={`${styles.toast} ${styles[toast.tone]}`} role="status">
            <Icon name={ICONS[toast.tone]} size={18} className={styles.icon} />
            <div className={styles.body}>
              <p className={styles.title}>{toast.title}</p>
              {toast.message && <p className={styles.message}>{toast.message}</p>}
            </div>
            <button
              type="button"
              className={styles.close}
              onClick={() => dismiss(toast.id)}
              aria-label="Dismiss notification"
            >
              <Icon name="close" size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

// The hook belongs with its provider; fast refresh still works for the provider.
// eslint-disable-next-line react-refresh/only-export-components
export function useToast(): ToastApi {
  const api = useContext(ToastContext)
  if (!api) throw new Error('useToast must be used inside <ToastProvider>')
  return api
}
