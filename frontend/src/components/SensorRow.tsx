import { Link } from 'react-router'
import { LABELS } from '../lib/status'
import { sensorDisplayState } from '../lib/aggregateStatus'
import { StatusIcon, statusTextColor } from './statusVisuals'
import type { LivePoint, SensorMeta, Threshold } from '../lib/types'

export function SensorRow({
  sensor,
  threshold,
  live,
}: {
  sensor: SensorMeta
  threshold: Threshold | null
  live: LivePoint | undefined
}) {
  const state = sensorDisplayState(threshold, live)

  return (
    <Link
      to={`/sensor/${sensor.sensor_code}`}
      className="flex items-center justify-between gap-4 rounded-xl border border-[var(--color-line)] p-4 outline-none transition-colors duration-200 ease-out hover:border-[var(--color-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
      style={{ background: 'var(--color-surface)' }}
    >
      <div>
        <p className="text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>
          {sensor.measurement_type.name}
        </p>
        <div
          className="mt-1 flex items-center gap-2 text-xs font-semibold"
          style={{ color: statusTextColor(state) }}
        >
          <StatusIcon state={state} />
          <span>{LABELS[state]}</span>
        </div>
      </div>

      <span className="font-mono text-lg font-semibold tabular-nums" style={{ color: 'var(--color-ink)' }}>
        {live ? live.value.toFixed(1) : '—'}{' '}
        <span className="text-sm font-medium" style={{ color: 'var(--color-muted)' }}>
          {sensor.unidade}
        </span>
      </span>
    </Link>
  )
}
