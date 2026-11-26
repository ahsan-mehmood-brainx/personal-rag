/**
 * Backend health, shared app-wide.
 *
 * Polls `GET /health` so the header indicator, the chat empty state and the documents page all
 * agree on whether the API is up, how many documents exist, and whether the index is usable.
 * Pages call `refresh()` after uploads and deletes so counts update immediately.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { ApiError, getHealth } from '../../api/client'
import type { HealthResponse } from '../../api/types'

export type HealthStatus = 'loading' | 'online' | 'offline'

interface HealthState {
  status: HealthStatus
  health: HealthResponse | null
  error: string | null
  refresh: () => Promise<void>
}

const HealthContext = createContext<HealthState | null>(null)

const POLL_MS = 30_000

export function HealthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<HealthStatus>('loading')
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const inFlight = useRef<AbortController | null>(null)

  const refresh = useCallback(async () => {
    inFlight.current?.abort()
    const controller = new AbortController()
    inFlight.current = controller
    try {
      const result = await getHealth(controller.signal)
      setHealth(result)
      setError(null)
      setStatus('online')
    } catch (err) {
      if (err instanceof ApiError && err.kind === 'aborted') return
      setError(err instanceof ApiError ? err.message : 'Health check failed.')
      setStatus('offline')
    }
  }, [])

  useEffect(() => {
    // Initial fetch and polling: the first run is deferred by a tick so it is a subscription
    // callback rather than a synchronous state update inside the effect body.
    const first = window.setTimeout(() => void refresh(), 0)
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refresh()
    }, POLL_MS)
    const onFocus = () => void refresh()
    window.addEventListener('focus', onFocus)
    return () => {
      window.clearTimeout(first)
      window.clearInterval(timer)
      window.removeEventListener('focus', onFocus)
      inFlight.current?.abort()
    }
  }, [refresh])

  const value = useMemo(
    () => ({ status, health, error, refresh }),
    [status, health, error, refresh],
  )
  return <HealthContext.Provider value={value}>{children}</HealthContext.Provider>
}

// The hook belongs with its provider; fast refresh still works for the provider.
// eslint-disable-next-line react-refresh/only-export-components
export function useHealth(): HealthState {
  const value = useContext(HealthContext)
  if (!value) throw new Error('useHealth must be used inside <HealthProvider>')
  return value
}
