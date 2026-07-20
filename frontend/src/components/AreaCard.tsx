import { useRef } from 'react'
import { areaAggregateState, sensorDisplayState, worstAlarmState, type AreaGroup } from '../lib/aggregateStatus'
import { DEFAULT_STALE_MS, freshness, type FreshnessTier } from '../lib/freshness'
import { useNow } from '../lib/useNow'
import { useSensorCarousel } from '../lib/useSensorCarousel'
import { StatusChip } from './StatusChip'
import { StatusDot } from './StatusDot'
import { statusTextColor } from './statusVisuals'
import type { LivePoint, Threshold } from '../lib/types'

// Janela de graca antes de escalar um sensor 'never' (nunca recebeu
// LivePoint nesta sessao) para 'offline' na agregacao da area. Proposta da
// doc: 2x staleMs. Medida a partir do MOUNT deste AreaCard -- e a melhor
// aproximacao disponivel no cliente de "desde quando estamos observando este
// sensor" quando nao ha nenhum ts para envelhecer (ver doc, "Limitacao
// honesta desta fase": sensor ja morto no load nao emite ts algum). Isto e
// uma escolha desta fase, nao um requisito da spec -- documentado aqui por
// ser a decisao mais visivel do T2.
const NEVER_GRACE_MS = 2 * DEFAULT_STALE_MS

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
  carouselIntervalMs,
}: {
  group: AreaGroup
  thresholdsByCode: Record<string, Threshold | null | undefined>
  liveByCode: Record<string, LivePoint | undefined>
  selectedSensorCode: string | null
  onSelectSensor: (code: string) => void
  hadAlarmToday: boolean
  carouselIntervalMs: number
}) {
  // mountedAtRef: referencia de "desde quando este AreaCard observa estes
  // sensores", usada so para escalar 'never' -> 'offline' apos a janela de
  // graca (ver NEVER_GRACE_MS acima). Sensores com live definido envelhecem
  // via ts real, sem depender disto.
  const mountedAtRef = useRef(Date.now())
  const now = useNow()

  const perSensor = group.sensors.map((s) => {
    const live = liveByCode[s.sensor_code]
    const display = sensorDisplayState(thresholdsByCode[s.sensor_code] ?? null, live)
    const rawFreshness = freshness(live, now)
    const effectiveFreshness: FreshnessTier =
      rawFreshness === 'never' && now - mountedAtRef.current > NEVER_GRACE_MS ? 'offline' : rawFreshness
    return { display, freshness: effectiveFreshness }
  })
  const aggregate = areaAggregateState(perSensor)
  const carousel = useSensorCarousel(group.sensors.length, carouselIntervalMs)
  const activeSensor = group.sensors[carousel.activeIndex] ?? group.sensors[0]
  const activeState = sensorDisplayState(
    thresholdsByCode[activeSensor.sensor_code] ?? null,
    liveByCode[activeSensor.sensor_code],
  )
  const activeLive = liveByCode[activeSensor.sensor_code]
  const activeSelected = activeSensor.sensor_code === selectedSensorCode

  return (
    <div
      className="flex h-full flex-col rounded-md p-4"
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
        borderLeft: `3px solid ${BORDER_COLOR[aggregate]}`,
      }}
      data-testid={`area-card-${group.area.area_code}`}
      onMouseEnter={carousel.pause}
      onMouseLeave={carousel.resume}
      onFocus={carousel.pause}
      onBlur={carousel.resume}
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

      {/* flex-1: preenche a altura restante do card para que áreas com 1
          sensor (sem carrossel) fiquem com a MESMA altura das de vários
          sensores — evita cards curtos e desalinhados do canto de resize.
          justify-between mantém o valor no topo e os dots no rodapé. */}
      <div className="mt-2 flex flex-1 flex-col justify-between">
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
