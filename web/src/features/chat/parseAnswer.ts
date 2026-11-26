/**
 * Splits answer text into paragraphs, bullet lists and numbered lists.
 * Pure, so it is unit-tested without rendering.
 */

export type Block =
  | { kind: 'paragraph'; lines: string[] }
  | { kind: 'bullets'; items: string[] }
  | { kind: 'numbered'; items: string[] }

const BULLET = /^\s*[-*•]\s+(.*)$/
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/

export function parseBlocks(text: string): Block[] {
  const blocks: Block[] = []
  for (const chunk of text.replace(/\r\n/g, '\n').split(/\n\s*\n/)) {
    const lines = chunk.split('\n').filter((l) => l.trim() !== '')
    let current: Block | null = null
    for (const line of lines) {
      const bullet = BULLET.exec(line)
      const numbered = bullet ? null : NUMBERED.exec(line)
      if (bullet?.[1] !== undefined) {
        if (current?.kind !== 'bullets') blocks.push((current = { kind: 'bullets', items: [] }))
        current.items.push(bullet[1])
      } else if (numbered?.[1] !== undefined) {
        if (current?.kind !== 'numbered') blocks.push((current = { kind: 'numbered', items: [] }))
        current.items.push(numbered[1])
      } else if (current && current.kind !== 'paragraph' && /^\s{2,}/.test(line)) {
        // Indented continuation of the previous list item.
        const last = current.items.length - 1
        current.items[last] = `${current.items[last]} ${line.trim()}`
      } else {
        if (current?.kind !== 'paragraph') blocks.push((current = { kind: 'paragraph', lines: [] }))
        current.lines.push(line.trim())
      }
    }
  }
  return blocks
}
