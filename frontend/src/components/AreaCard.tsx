import { sensorDisplayState, worstAlarmState, type AreaGroup } from '../lib/aggregateStatus'
import { useSensorCarousel } from '../lib/useSensorCarousel'
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

const CAROUSEL_INTERVAL_MS = 3000

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
  const carousel = useSensorCarousel(group.sensors.length, CAROUSEL_INTERVAL_MS)
  const activeSensor = group.sensors[carousel.activeIndex] ?? group.sensors[0]
  const activeState = sensorDisplayState(
    thresholdsByCode[activeSensor.sensor_code] ?? null,
    liveByCode[activeSensor.sensor_code],
  )
  const activeLive = liveByCode[activeSensor.sensor_code]
  const activeSelected = activeSensor.sensor_code === selectedSensorCode

  return (
    <div
      className="rounded-md p-4"
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
        borderLeft: `3px solid ${BORDER_COLOR[aggregate]}`,
      }}
      data-testid={`area-card-${group.area.area_code}`}
      onMouseEnter={carousel.pause}
      onMouseLeave={carousel.resume}
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

      <div className="mt-2">
        <button
          type="button"
          onClick={() => onSelectSensor(activeSensor.sensor_code)}
          className="flex w-full flex-col items-start gap-1 rounded-md px-2 py-2 text-left outline-none transition-colors duration-200 ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
          style={{ background: activeSelected ? 'var(--color-panel)' : 'transparent' }}
        >
          <span className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--color-muted)' }}>
            <StatusDot state={activeState} />
            {activeSensor.measurement_type.name}
          </span>
          <span
            className="font-mono text-3xl font-bold tabular-nums"
            style={{
              color: activeState === 'ok' || activeState === 'unknown' ? 'var(--color-ink)' : statusTextColor(activeState),
            }}
          >
            {activeLive ? activeLive.value.toFixed(1) : '—'}{' '}
            <span className="text-base font-medium">{activeSensor.unidade}</span>
          </span>
        </button>

        {group.sensors.length > 1 && (
          <div className="mt-2 flex items-center justify-center gap-1.5" role="tablist" aria-label="Sensores da área">
            {group.sensors.map((s, i) => (
              <button
                key={s.sensor_code}
                type="button"
                role="tab"
                aria-selected={i === carousel.activeIndex}
                aria-label={s.measurement_type.name}
                onClick={() => carousel.setActiveIndex(i)}
                className="size-1.5 rounded-full transition-colors duration-200 ease-out motion-reduce:transition-none"
                style={{ background: i === carousel.activeIndex ? 'var(--color-ink)' : 'var(--color-line)' }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
