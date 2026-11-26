/**
 * "Allow External Search" toggle. Defaults to OFF.
 *
 * The frontend never searches anything itself; the toggle only decides what is sent to the
 * backend. The current backend has no external-search capability (`capabilities.externalSearch`
 * is false), so the switch is shown locked OFF with the reason, instead of pretending to work.
 */
import { Badge } from '../../components/Badge'
import { Icon } from '../../components/Icon'
import { Switch } from '../../components/Switch'
import styles from './ExternalSearchToggle.module.css'

interface ExternalSearchToggleProps {
  checked: boolean
  available: boolean
  onChange: (value: boolean) => void
}

export function ExternalSearchToggle({ checked, available, onChange }: ExternalSearchToggleProps) {
  const description = !available ? (
    <>
      <Icon name="lock" size={11} className={styles.lock} /> Answers come only from your uploaded
      documents. External search isn&apos;t supported by this backend yet.
    </>
  ) : checked ? (
    'The assistant may use outside information in addition to your documents.'
  ) : (
    'Answers come only from your uploaded documents.'
  )

  return (
    <div className={styles.wrap}>
      <Switch
        checked={checked}
        onChange={onChange}
        disabled={!available}
        label="Allow External Search"
        adornment={<Badge tone={checked ? 'accent' : 'neutral'}>{checked ? 'On' : 'Off'}</Badge>}
        description={description}
        testId="external-search-toggle"
      />
    </div>
  )
}
