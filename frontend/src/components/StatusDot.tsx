import type { StatusResult } from '../lib/status'

type State = StatusResult['state']

const DOT: Record<State, string> = {
  ok: 'var(--color-good)',
  warn: 'var(--color-warn)',
  crit: 'var(--color-crit)',
  unknown: 'var(--color-muted)',
}

export function StatusDot({ state }: { state: State }) {
  return (
    <span
      aria-hidden="true"
      className="inline-block size-1.5 shrink-0 rounded-full"
      style={{ background: DOT[state] }}
    />
  )
}
