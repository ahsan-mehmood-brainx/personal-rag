/**
 * "Allow External Search" toggle, under the input. Defaults to OFF.
 *
 * The frontend never searches anything itself; the value is sent with each question as
 * `allow_external_search`. It can be flipped at any point in a conversation, including while
 * an answer is loading: each question uses the value it was sent with.
 */
import { Badge } from '../../components/Badge'
import { Switch } from '../../components/Switch'
import styles from './ExternalSearchToggle.module.css'

interface ExternalSearchToggleProps {
  checked: boolean
  onChange: (value: boolean) => void
}

export function ExternalSearchToggle({ checked, onChange }: ExternalSearchToggleProps) {
  return (
    <div className={styles.wrap}>
      <Switch
        checked={checked}
        onChange={onChange}
        label="Allow External Search"
        adornment={<Badge tone={checked ? 'accent' : 'neutral'}>{checked ? 'On' : 'Off'}</Badge>}
        description={
          checked
            ? 'General questions are answered with a web search. Questions about you still use only your documents.'
            : 'Answers come only from your uploaded documents.'
        }
        testId="external-search-toggle"
      />
    </div>
  )
}
