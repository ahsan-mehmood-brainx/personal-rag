/**
 * Light / dark / system theme. The choice is stored per browser; "system" follows the OS.
 * index.html applies the stored value before first paint to avoid a flash.
 */
import { useCallback, useEffect, useState } from 'react'
import { readString, writeString } from '../lib/storage'

export type ThemeChoice = 'system' | 'light' | 'dark'

const KEY = 'prag.theme'
const ORDER: ThemeChoice[] = ['system', 'light', 'dark']

function initial(): ThemeChoice {
  const stored = readString(KEY)
  return stored === 'light' || stored === 'dark' ? stored : 'system'
}

export function useTheme() {
  const [theme, setTheme] = useState<ThemeChoice>(initial)

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') delete root.dataset.theme
    else root.dataset.theme = theme
    writeString(KEY, theme === 'system' ? null : theme)
  }, [theme])

  const cycle = useCallback(() => {
    setTheme((current) => ORDER[(ORDER.indexOf(current) + 1) % ORDER.length] ?? 'system')
  }, [])

  return { theme, cycle }
}
