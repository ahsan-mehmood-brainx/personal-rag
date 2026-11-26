/** Expandable "Sources" and "Internals" sections under an assistant answer. */
import type { DebugInfo, Source } from '../../api/types'
import { Icon } from '../../components/Icon'
import { pluralize } from '../../lib/format'
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

export function InternalsPanel({ debug }: { debug: DebugInfo }) {
  const latency = Object.entries(debug.latency_ms)
  const tokens = Object.entries(debug.token_usage)
  return (
    <details className={styles.details}>
      <summary className={styles.summary}>
        <Icon name="chevron" size={14} className={styles.chevron} />
        Internals
      </summary>
      <dl className={styles.internals}>
        <dt>Classifier</dt>
        <dd>
          <code>{debug.classifier_category ?? 'not run'}</code>
          {debug.classifier_reason && <span> · {debug.classifier_reason}</span>}
        </dd>

        <dt>Retrieved</dt>
        <dd>
          {debug.retrieved.length === 0 ? (
            'No retrieval for this question.'
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <caption>
                  {pluralize(debug.retrieved.length, 'chunk')}, threshold {debug.threshold.toFixed(2)}
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Similarity</th>
                    <th scope="col">Result</th>
                    <th scope="col">Document</th>
                    <th scope="col">Section</th>
                  </tr>
                </thead>
                <tbody>
                  {debug.retrieved.map((hit) => (
                    <tr key={hit.chunk_id}>
                      <td>{hit.similarity.toFixed(4)}</td>
                      <td className={hit.kept ? styles.kept : styles.below}>
                        {hit.kept ? 'kept' : 'below'}
                      </td>
                      <td>{hit.filename}</td>
                      <td>{hit.section}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </dd>

        {latency.length > 0 && (
          <>
            <dt>Latency</dt>
            <dd>{latency.map(([step, ms]) => `${step} ${Math.round(ms)} ms`).join(' · ')}</dd>
          </>
        )}

        {tokens.length > 0 && (
          <>
            <dt>Tokens</dt>
            <dd>
              {tokens
                .map(([step, u]) => `${step} ${u.input_tokens} in / ${u.output_tokens} out`)
                .join(' · ')}
            </dd>
          </>
        )}
      </dl>
    </details>
  )
}
