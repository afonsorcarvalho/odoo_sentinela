import { stateLabel, type StatusResult } from '../lib/status'
import type { StatusLeitura } from '../lib/types'
import { StatusIcon } from './statusVisuals'

type State = StatusResult['state']

const SOFT_BG: Record<State, string> = {
  ok: 'var(--color-good-soft)',
  warn: 'var(--color-warn-soft)',
  crit: 'var(--color-crit-soft)',
  unknown: 'var(--color-panel)',
  fault: 'var(--color-crit-soft)',
  invalid: 'var(--color-panel)',
}
const SOLID_TEXT: Record<State, string> = {
  ok: 'var(--color-good)',
  warn: 'var(--color-warn)',
  crit: 'var(--color-crit)',
  unknown: 'var(--color-muted)',
  fault: 'var(--color-crit)',
  invalid: 'var(--color-muted)',
}

export function StatusChip({ state, statusLeitura }: { state: State; statusLeitura?: StatusLeitura }) {
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-bold"
      style={{ background: SOFT_BG[state], color: SOLID_TEXT[state] }}
    >
      <StatusIcon state={state} />
      {stateLabel(state, statusLeitura)}
    </span>
  )
}
