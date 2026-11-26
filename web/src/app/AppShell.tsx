/** Top-level layout: header with brand, Chat / Documents navigation, health and theme. */
import { NavLink, Outlet } from 'react-router-dom'
import { Icon } from '../components/Icon'
import { HealthIndicator } from '../features/health/HealthIndicator'
import { ROUTES } from './routes'
import { useTheme, type ThemeChoice } from './useTheme'
import styles from './AppShell.module.css'

const THEME_META: Record<ThemeChoice, { icon: 'monitor' | 'sun' | 'moon'; label: string }> = {
  system: { icon: 'monitor', label: 'Theme: system' },
  light: { icon: 'sun', label: 'Theme: light' },
  dark: { icon: 'moon', label: 'Theme: dark' },
}

export function AppShell() {
  const { theme, cycle } = useTheme()
  const meta = THEME_META[theme]

  return (
    <div className={styles.shell}>
      <a href="#main" className={styles.skipLink}>
        Skip to content
      </a>
      <header className={styles.header}>
        <div className={styles.brand}>
          <span className={styles.logo} aria-hidden="true">
            <Icon name="chat" size={18} />
          </span>
          <span className={styles.brandText}>Personal RAG</span>
        </div>

        <nav className={styles.nav} aria-label="Main">
          <NavLink to={ROUTES.chat} className={({ isActive }) => `${styles.navLink} ${isActive ? styles.active : ''}`}>
            <Icon name="chat" size={17} />
            <span>Chat</span>
          </NavLink>
          <NavLink
            to={ROUTES.documents}
            className={({ isActive }) => `${styles.navLink} ${isActive ? styles.active : ''}`}
          >
            <Icon name="file" size={17} />
            <span>Documents</span>
          </NavLink>
        </nav>

        <div className={styles.tools}>
          <HealthIndicator />
          <button
            type="button"
            className={styles.themeButton}
            onClick={cycle}
            aria-label={`${meta.label}. Change theme`}
            title={meta.label}
          >
            <Icon name={meta.icon} size={18} />
          </button>
        </div>
      </header>
      <main id="main" className={styles.main} tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  )
}
