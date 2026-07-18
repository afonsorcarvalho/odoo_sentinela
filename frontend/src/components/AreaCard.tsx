import { LABELS } from '../lib/status'
import { sensorDisplayState, worstAlarmState, type AreaGroup } from '../lib/aggregateStatus'
import { StatusIcon, statusTextColor } from './statusVisuals'
import type { LivePoint, Threshold } from '../lib/types'

export function AreaCard({
  group,
  thresholdsByCode,
  liveByCode,
}: {
  group: AreaGroup
  thresholdsByCode: Record<string, Threshold | null | undefined>
  liveByCode: Record<string, LivePoint | undefined>
}) {
  const states = group.sensors.map((s) =>
    sensorDisplayState(thresholdsByCode[s.sensor_code] ?? null, liveByCode[s.sensor_code]),
  )
  const aggregate = worstAlarmState(states)
  const critCount = states.filter((s) => s === 'crit').length

  return (
    <div
      className="rounded-2xl p-5"
      style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}
      data-testid={`area-card-${group.area.area_code}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold" style={{ color: 'var(--color-ink)' }}>
            {group.area.name}
          </h2>
          <p className="mt-0.5 text-xs" style={{ color: 'var(--color-muted)' }}>
            {group.area.category}
          </p>
        </div>
        {critCount > 0 && (
          <span
            className="rounded-full px-2 py-0.5 text-xs font-semibold"
            style={{ background: 'var(--color-panel)', color: 'var(--color-crit)' }}
          >
            {critCount} {critCount === 1 ? 'alarme' : 'alarmes'}
          </span>
        )}
      </div>

      <div
        className="mt-4 flex items-center gap-2 text-sm font-semibold"
        style={{ color: statusTextColor(aggregate) }}
      >
        <StatusIcon state={aggregate} />
        <span>{LABELS[aggregate]}</span>
      </div>
    </div>
  )
}
