import { LABELS, type StatusResult } from '../lib/status'
import { StatusIcon } from './statusVisuals'

type State = StatusResult['state']

const SOFT_BG: Record<State, string> = {
  ok: 'var(--color-good-soft)',
  warn: 'var(--color-warn-soft)',
  crit: 'var(--color-crit-soft)',
  unknown: 'var(--color-panel)',
}
const SOLID_TEXT: Record<State, string> = {
  ok: 'var(--color-good)',
  warn: 'var(--color-warn)',
  crit: 'var(--color-crit)',
  unknown: 'var(--color-muted)',
}

export function StatusChip({ state }: { state: State }) {
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-bold"
      style={{ background: SOFT_BG[state], color: SOLID_TEXT[state] }}
    >
      <StatusIcon state={state} />
      {LABELS[state]}
    </span>
  )
}
