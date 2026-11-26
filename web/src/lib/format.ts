/** Display formatting helpers. Pure functions, so they are easy to test. */

const dateTimeFormat = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

const dateFormat = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
})

function parse(iso: string): Date | null {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDateTime(iso: string): string {
  const date = parse(iso)
  return date ? dateTimeFormat.format(date) : 'Unknown date'
}

export function formatDate(iso: string): string {
  const date = parse(iso)
  return date ? dateFormat.format(date) : 'Unknown date'
}

/** "Just now", "5 min ago", "3 h ago", "Yesterday", then a short date. */
export function formatRelative(iso: string, now: Date = new Date()): string {
  const date = parse(iso)
  if (!date) return ''
  const seconds = Math.round((now.getTime() - date.getTime()) / 1000)
  if (seconds < 60) return 'Just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  if (hours < 48) return 'Yesterday'
  return formatDate(iso)
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  const mb = bytes / (1024 * 1024)
  return `${Number.isInteger(mb) ? mb : mb.toFixed(1)} MB`
}

/** Lower-case extension with the dot, or "" when there is none. */
export function extensionOf(filename: string): string {
  const dot = filename.lastIndexOf('.')
  return dot > 0 && dot < filename.length - 1 ? filename.slice(dot).toLowerCase() : ''
}

const TYPE_LABELS: Record<string, string> = {
  '.pdf': 'PDF',
  '.docx': 'Word',
  '.txt': 'Text',
  '.md': 'Markdown',
}

export function fileTypeLabel(filename: string): string {
  const ext = extensionOf(filename)
  return TYPE_LABELS[ext] ?? (ext ? ext.slice(1).toUpperCase() : 'File')
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`
}
