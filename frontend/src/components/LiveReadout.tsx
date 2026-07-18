import { computeStatus, LABELS, type StatusResult } from '../lib/status'
import type { Threshold, AlarmState } from '../lib/types'
import { ToleranceRail } from './ToleranceRail'
import { StatusIcon, statusTextColor } from './statusVisuals'

type State = StatusResult['state']

export function LiveReadout({
  value,
  unidade,
  threshold,
  state,
}: {
  value: number | null
  unidade: string
  threshold: Threshold | null
  state?: AlarmState
}) {
  const derived: StatusResult =
    value !== null
      ? computeStatus(value, threshold)
      : { state: 'unknown', label: LABELS.unknown, position: null }
  const st: State = state ?? derived.state

  return (
    <div
      className="rounded-2xl p-6 md:p-7"
      style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}
    >
      <div className="flex items-end gap-2">
        <span
          className="font-mono text-5xl font-semibold leading-none tracking-tight tabular-nums transition-colors duration-200 ease-out motion-reduce:transition-none md:text-6xl"
          style={{ color: 'var(--color-ink)' }}
        >
          {value === null ? '—' : value.toFixed(1)}
        </span>
        <span
          className="pb-1 text-lg font-medium uppercase tracking-wide md:text-xl"
          style={{ color: 'var(--color-muted)' }}
        >
          {unidade}
        </span>
      </div>

      <div
        className="mt-4 flex items-center gap-2 text-sm font-semibold transition-colors duration-200 ease-out motion-reduce:transition-none"
        style={{ color: statusTextColor(st) }}
      >
        <StatusIcon state={st} />
        <span>{LABELS[st]}</span>
      </div>

      <div className="mt-5">
        <ToleranceRail
          position={derived.position}
          state={st}
          min={threshold?.limite_min}
          max={threshold?.limite_max}
        />
      </div>
    </div>
  )
}
