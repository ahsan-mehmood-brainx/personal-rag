/**
 * Renders answer text with light formatting: paragraphs, bullet and numbered lists, **bold**.
 *
 * Built from React elements, never `innerHTML`, so model output (which can echo document
 * text) cannot inject markup. Anything that is not recognised renders as plain text.
 */
import type { ReactNode } from 'react'
import { parseBlocks } from './parseAnswer'
import styles from './AnswerText.module.css'

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') && part.length > 4 ? (
      <strong key={i}>{part.slice(2, -2)}</strong>
    ) : (
      part
    ),
  )
}

export function AnswerText({ text }: { text: string }) {
  return (
    <div className={styles.answer}>
      {parseBlocks(text).map((block, i) => {
        if (block.kind === 'bullets') {
          return (
            <ul key={i}>
              {block.items.map((item, j) => (
                <li key={j}>{inline(item)}</li>
              ))}
            </ul>
          )
        }
        if (block.kind === 'numbered') {
          return (
            <ol key={i}>
              {block.items.map((item, j) => (
                <li key={j}>{inline(item)}</li>
              ))}
            </ol>
          )
        }
        return (
          <p key={i}>
            {block.lines.map((line, j) => (
              <span key={j}>
                {j > 0 && <br />}
                {inline(line)}
              </span>
            ))}
          </p>
        )
      })}
    </div>
  )
}
