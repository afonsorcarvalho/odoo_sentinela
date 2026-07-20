import { computeStatus, LABELS, type StatusResult } from '../lib/status'
import type { AreaGroup } from '../lib/aggregateStatus'
import type { AlarmState, HistoryResponse, LivePoint, Threshold, Window } from '../lib/types'
import { ToleranceRail } from './ToleranceRail'
import { StatusIcon, statusTextColor } from './statusVisuals'
import { WindowSelector } from './WindowSelector'
import { TimeSeriesChart } from './TimeSeriesChart'

export function SensorDetailPanel({
  group, selectedCode, onSelectSensor, threshold, unidade, value, state,
  window, onWindowChange, history, tail,
}: {
  group: AreaGroup
  selectedCode: string
  onSelectSensor: (code: string) => void
  threshold: Threshold | null
  unidade: string
  value: number | null
  state?: AlarmState
  window: Window
  onWindowChange: (w: Window) => void
  history: HistoryResponse | undefined
  tail: LivePoint[]
}) {
  const selected = group.sensors.find((s) => s.sensor_code === selectedCode)
  const derived: StatusResult =
    value !== null
      ? computeStatus(value, threshold)
      : { state: 'unknown', label: LABELS.unknown, position: null }
  const st = state ?? derived.state

  return (
    <div className="flex h-full flex-col rounded-md p-4" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold" style={{ color: 'var(--color-ink)' }}>Detalhe do sensor</h2>
          <p className="mt-0.5 font-mono text-sm" style={{ color: 'var(--color-muted)' }}>
            {group.area.name} · {selected?.measurement_type.name}
          </p>
        </div>
        <div className="flex gap-1.5">
          {group.sensors.map((s) => {
            const on = s.sensor_code === selectedCode
            return (
              <button
                key={s.sensor_code}
                type="button"
                onClick={() => onSelectSensor(s.sensor_code)}
                className="min-h-11 rounded-md px-3 text-sm font-semibold outline-none transition-colors duration-200 ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
                style={on
                  ? { background: 'var(--color-primary)', color: 'var(--color-surface)' }
                  : { border: '1px solid var(--color-line)', color: 'var(--color-muted)' }}
              >
                {s.measurement_type.name}
              </button>
            )
          })}
        </div>
      </div>

      <div className="mt-4 flex items-end gap-2">
        <span className="font-mono text-5xl font-semibold leading-none tabular-nums md:text-6xl" style={{ color: 'var(--color-ink)' }}>
          {value === null ? '—' : value.toFixed(1)}
        </span>
        <span className="pb-1 text-lg font-medium uppercase" style={{ color: 'var(--color-muted)' }}>{unidade}</span>
      </div>
      <div className="mt-2 flex items-center gap-2 text-sm font-semibold" style={{ color: statusTextColor(st) }}>
        <StatusIcon state={st} />
        <span>{LABELS[st]}</span>
      </div>
      <div className="mt-4">
        <ToleranceRail position={derived.position} state={st} min={threshold?.limite_min} max={threshold?.limite_max} />
      </div>

      <div className="mt-5 mb-3 flex justify-end">
        <WindowSelector value={window} onChange={onWindowChange} />
      </div>
      <div data-testid="sensor-detail-chart-wrapper" className="min-h-0 flex-1">
        <TimeSeriesChart history={history} threshold={threshold} tail={tail} />
      </div>
    </div>
  )
}
