/** Expandable "Sources" and "Web sources" sections under an assistant answer. */
import type { Source, WebSource } from '../../api/types'
import { Icon } from '../../components/Icon'
import styles from './ResponseDetails.module.css'

function pageText(page: number | null): string | null {
  return page === null ? null : `page ${page}`
}

export function SourcesList({ sources }: { sources: Source[] }) {
  if (sources.length === 0) return null
  return (
    <details className={styles.details}>
      <summary className={styles.summary}>
        <Icon name="chevron" size={14} className={styles.chevron} />
        Sources ({sources.length})
      </summary>
      <ul className={styles.sources}>
        {sources.map((source) => (
          <li key={source.label} className={styles.source}>
            <div className={styles.sourceHead}>
              <span className={styles.label}>{source.label}</span>
              <span className={styles.sourceFile}>{source.filename}</span>
            </div>
            <p className={styles.sourceMeta}>
              {[source.section, pageText(source.page), `similarity ${source.similarity.toFixed(3)}`]
                .filter(Boolean)
                .join(' · ')}
            </p>
            <blockquote className={styles.excerpt}>{source.excerpt}</blockquote>
          </li>
        ))}
      </ul>
    </details>
  )
}

/** Only http(s) links are rendered as links; anything else (for example `javascript:`) is not. */
function safeHttpUrl(raw: string): URL | null {
  try {
    const url = new URL(raw)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url : null
  } catch {
    return null
  }
}

interface WebLink {
  href: string
  hostname: string
  title: string
}

/** Safe links, deduped on the normalized href (`https://a.com` and `https://a.com/` are one). */
function toWebLinks(sources: WebSource[]): WebLink[] {
  const byHref = new Map<string, WebLink>()
  for (const source of sources) {
    const url = safeHttpUrl(source.url)
    if (!url || byHref.has(url.href)) continue
    byHref.set(url.href, { href: url.href, hostname: url.hostname, title: source.title.trim() || url.hostname })
  }
  return [...byHref.values()]
}

export function WebSourcesList({ sources }: { sources: WebSource[] }) {
  const links = toWebLinks(sources)
  if (links.length === 0) return null
  return (
    <details className={styles.details}>
      <summary className={styles.summary}>
        <Icon name="chevron" size={14} className={styles.chevron} />
        Web sources ({links.length})
      </summary>
      <ul className={styles.sources}>
        {links.map((link) => (
          <li key={link.href} className={styles.source}>
            <a className={styles.webLink} href={link.href} target="_blank" rel="noopener noreferrer">
              {link.title}
            </a>
            <p className={styles.sourceMeta}>{link.hostname}</p>
          </li>
        ))}
      </ul>
    </details>
  )
}
