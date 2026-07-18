import { sensorDisplayState, worstAlarmState, type AreaGroup } from '../lib/aggregateStatus'
import { StatusChip } from './StatusChip'
import { StatusDot } from './StatusDot'
import { statusTextColor } from './statusVisuals'
import type { LivePoint, Threshold } from '../lib/types'

const BORDER_COLOR: Record<ReturnType<typeof worstAlarmState>, string> = {
  ok: 'var(--color-line)',
  warn: 'var(--color-warn)',
  crit: 'var(--color-crit)',
  unknown: 'var(--color-line)',
}

export function AreaCard({
  group,
  thresholdsByCode,
  liveByCode,
  selectedSensorCode,
  onSelectSensor,
  hadAlarmToday,
}: {
  group: AreaGroup
  thresholdsByCode: Record<string, Threshold | null | undefined>
  liveByCode: Record<string, LivePoint | undefined>
  selectedSensorCode: string | null
  onSelectSensor: (code: string) => void
  hadAlarmToday: boolean
}) {
  const states = group.sensors.map((s) =>
    sensorDisplayState(thresholdsByCode[s.sensor_code] ?? null, liveByCode[s.sensor_code]),
  )
  const aggregate = worstAlarmState(states)

  return (
    <div
      className="rounded-md p-4"
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
        borderLeft: `3px solid ${BORDER_COLOR[aggregate]}`,
      }}
      data-testid={`area-card-${group.area.area_code}`}
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold" style={{ color: 'var(--color-ink)' }}>
          {group.area.name}
        </h2>
        <div className="flex items-center gap-2">
          {hadAlarmToday && (
            <span
              aria-label="Houve não conformidade hoje"
              className="flex size-[18px] items-center justify-center rounded-full text-xs font-bold"
              style={{ background: 'var(--color-warn-soft)', color: 'var(--color-warn)' }}
            >
              !
            </span>
          )}
          <StatusChip state={aggregate} />
        </div>
      </div>

      <div className="mt-3 border-t" style={{ borderColor: 'var(--color-line)' }} />

      <div className="mt-2 space-y-1">
        {group.sensors.map((s) => {
          const state = sensorDisplayState(thresholdsByCode[s.sensor_code] ?? null, liveByCode[s.sensor_code])
          const selected = s.sensor_code === selectedSensorCode
          const live = liveByCode[s.sensor_code]
          return (
            <button
              key={s.sensor_code}
              type="button"
              onClick={() => onSelectSensor(s.sensor_code)}
              className="flex min-h-11 w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left outline-none transition-colors duration-200 ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
              style={{ background: selected ? 'var(--color-panel)' : 'transparent' }}
            >
              <span className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--color-muted)' }}>
                <StatusDot state={state} />
                {s.measurement_type.name}
              </span>
              <span
                className="font-mono text-sm font-semibold tabular-nums"
                style={{ color: state === 'ok' || state === 'unknown' ? 'var(--color-ink)' : statusTextColor(state) }}
              >
                {live ? live.value.toFixed(1) : '—'} {s.unidade}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
