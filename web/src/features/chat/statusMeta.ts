import type { AskStatus } from '../../api/types'
import type { Tone } from '../../components/Badge'

/** Badge text and color for every `/ask` status (spec section 2, "Behavior contract"). */
export const STATUS_META: Record<AskStatus, { label: string; tone: Tone }> = {
  answered: { label: 'Answered', tone: 'success' },
  not_found: { label: 'Not in your documents', tone: 'warning' },
  out_of_scope: { label: 'Out of scope', tone: 'danger' },
  meta: { label: 'Info', tone: 'info' },
  no_documents: { label: 'No documents', tone: 'neutral' },
  error: { label: 'Error', tone: 'danger' },
}
