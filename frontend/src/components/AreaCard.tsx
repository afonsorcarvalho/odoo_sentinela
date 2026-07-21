import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from 'react'
import { areaAggregateState, sensorDisplayState, worstAlarmState, type AreaGroup } from '../lib/aggregateStatus'
import { DEFAULT_STALE_MS, freshness, type FreshnessTier } from '../lib/freshness'
import { useCountUp } from '../lib/useCountUp'
import { useFitText } from '../lib/useFitText'
import { useNow } from '../lib/useNow'
import { useSensorCarousel, usePrefersReducedMotion } from '../lib/useSensorCarousel'
import { DisconnectIcon, FreshnessBadge } from './FreshnessBadge'
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

type Sensor = AreaGroup['sensors'][number]

function valueOpacityFor(fr: FreshnessTier): number {
  // 'stale' fica visivel mas suspeito; 'offline' quase apagado (o valor vira
  // '—' de qualquer forma, pois nao deve mais ser lido como leitura atual).
  return fr === 'stale' ? 0.55 : fr === 'offline' ? 0.4 : 1
}

// Leitura de UM sensor: nome (escala via cqmin) + valor escalado p/ preencher
// a caixa (useFitText; a unidade fica fora, no rodape do card). O valor tem
// count-up proprio: como cada instancia e keyed por sensor no call-site,
// leituras novas do MESMO sensor mantem a instancia (o numero "rola" ate o
// novo valor), e a troca de sensor monta uma instancia nova (o numero ja
// entra no valor certo, sem contar entre sensores diferentes).
function AreaSensorReadout({
  sensor,
  live,
  threshold,
  freshness: fr,
  ageMs,
  className,
  style,
}: {
  sensor: Sensor
  live: LivePoint | undefined
  threshold: Threshold | null | undefined
  freshness: FreshnessTier
  ageMs: number | undefined
  className?: string
  style?: CSSProperties
}) {
  const state = sensorDisplayState(threshold ?? null, live)
  // offline (real ou escalado de never) faz o StatusDot refletir o estado da
  // CONEXAO, nao mais o alarm_state antigo do ultimo valor conhecido.
  const dotState = fr === 'offline' ? 'crit' : state
  const opacity = valueOpacityFor(fr)
  const rawValue = fr === 'offline' ? null : (live?.value ?? null)
  const animated = useCountUp(rawValue)
  const displayValue = animated != null ? animated.toFixed(1) : '—'
  // O valor escala para preencher a caixa (largura e altura). Reajusta quando
  // muda o comprimento do numero (mais/menos digitos) ou a leitura bruta.
  const { boxRef, textRef, fit } = useFitText({ min: 9 })
  useLayoutEffect(() => {
    fit()
  }, [fit, rawValue, displayValue.length])

  return (
    <div className={`flex min-h-0 flex-col gap-0.5${className ? ` ${className}` : ''}`} style={style}>
      {/* Nome do sensor: escala com o card via container-query (cqmin, relativo
          ao @container do AreaCard). Status dot e badge de freshness tem
          tamanho proprio (indicadores). */}
      <span
        className="flex items-center gap-2 font-medium text-[clamp(0.72rem,4.5cqmin,1.15rem)]"
        style={{ color: 'var(--color-muted)' }}
      >
        <span data-testid="sensor-status-dot">
          <StatusDot state={dotState} />
        </span>
        {sensor.measurement_type.name}
        {fr !== 'fresh' && <FreshnessBadge tier={fr} ageMs={ageMs} />}
      </span>
      <div ref={boxRef} className="flex min-h-0 flex-1 items-center overflow-hidden">
        <span
          ref={textRef}
          className="inline-block whitespace-nowrap font-mono font-bold leading-none tabular-nums"
          style={{
            color: state === 'ok' || state === 'unknown' ? 'var(--color-ink)' : statusTextColor(state),
            opacity,
          }}
        >
          {displayValue}
        </span>
      </div>
    </div>
  )
}

export function AreaCard({
  group,
  thresholdsByCode,
  liveByCode,
  selectedSensorCode,
  onSelectSensor,
  hadAlarmToday,
  carouselIntervalMs,
  carouselTransitionMs = 300,
}: {
  group: AreaGroup
  thresholdsByCode: Record<string, Threshold | null | undefined>
  liveByCode: Record<string, LivePoint | undefined>
  selectedSensorCode: string | null
  onSelectSensor: (code: string) => void
  hadAlarmToday: boolean
  carouselIntervalMs: number
  // Duração (ms) da animação de troca de sensor do carrossel (o empurrão
  // vertical). Config global (config.carousel_transition_ms via AreaWidget);
  // default 300. Maior = transição mais lenta.
  carouselTransitionMs?: number
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
  // Marcador de offline no cabecalho: distingue "warn/crit por offline" de
  // "warn por valor perto do limite". Nao restrito a aggregate==='warn': um
  // sensor offline e sempre informacao acionavel p/ o operador.
  const anyOffline = perSensor.some((p) => p.freshness === 'offline')
  const carousel = useSensorCarousel(group.sensors.length, carouselIntervalMs)
  const reducedMotion = usePrefersReducedMotion()
  const activeIndex = carousel.activeIndex
  const activeSensor = group.sensors[activeIndex] ?? group.sensors[0]
  const activeSelected = activeSensor.sensor_code === selectedSensorCode
  const activeFreshness: FreshnessTier = perSensor[activeIndex]?.freshness ?? 'never'

  // Empurrao vertical na troca de sensor: renderiza o sensor que SAI e o que
  // ENTRA ao mesmo tempo, deslizando juntos (novo entra de baixo e empurra o
  // antigo p/ cima e p/ fora). Duracao = carouselTransitionMs. Sob
  // prefers-reduced-motion, troca seca (nunca marca leaving).
  const [leavingIndex, setLeavingIndex] = useState<number | null>(null)
  const prevIndexRef = useRef(activeIndex)
  useEffect(() => {
    if (prevIndexRef.current === activeIndex) return
    const prev = prevIndexRef.current
    prevIndexRef.current = activeIndex
    if (reducedMotion || group.sensors.length <= 1) {
      setLeavingIndex(null)
      return
    }
    setLeavingIndex(prev)
    const t = setTimeout(() => setLeavingIndex(null), carouselTransitionMs)
    return () => clearTimeout(t)
  }, [activeIndex, reducedMotion, carouselTransitionMs, group.sensors.length])

  function readoutProps(i: number) {
    const s = group.sensors[i]
    const live = liveByCode[s.sensor_code]
    return {
      sensor: s,
      live,
      threshold: thresholdsByCode[s.sensor_code],
      freshness: perSensor[i]?.freshness ?? ('never' as FreshnessTier),
      ageMs: live ? now - live.ts : undefined,
    }
  }

  const transitioning = leavingIndex != null && !reducedMotion

  return (
    <div
      className="@container relative flex h-full flex-col rounded-md p-3"
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
          {anyOffline && (
            <span
              aria-label="Sensor offline nesta área"
              className="flex size-[18px] items-center justify-center rounded-full"
              style={{ background: 'var(--color-crit-soft)', color: 'var(--color-crit)' }}
            >
              <DisconnectIcon />
            </span>
          )}
          <StatusChip state={aggregate} />
        </div>
      </div>

      <div className="mt-2 border-t" style={{ borderColor: 'var(--color-line)' }} />

      {/* flex-1: preenche a altura restante do card para que áreas com 1 sensor
          (sem carrossel) fiquem com a MESMA altura das de vários sensores.
          items-stretch: a coluna de dots (à esquerda) e o viewport do valor
          esticam à altura da linha. */}
      <div className="mt-1 flex min-h-0 flex-1 items-stretch gap-3">
        {group.sensors.length > 1 && (
          <div
            className="flex flex-col items-center justify-center gap-1.5"
            role="tablist"
            aria-label="Sensores da área"
          >
            {group.sensors.map((s, i) => (
              <button
                key={s.sensor_code}
                type="button"
                role="tab"
                aria-selected={i === activeIndex}
                aria-label={s.measurement_type.name}
                onClick={() => carousel.setActiveIndex(i)}
                className="size-1.5 rounded-full transition-[background,transform] duration-200 ease-out motion-reduce:transition-none"
                style={{
                  background: i === activeIndex ? 'var(--color-ink)' : 'var(--color-line)',
                  transform: i === activeIndex ? 'scale(1.15)' : 'scale(1)',
                }}
              />
            ))}
          </div>
        )}
        <button
          type="button"
          onClick={() => onSelectSensor(activeSensor.sensor_code)}
          className="flex min-h-0 min-w-0 flex-1 flex-col rounded-md px-2 py-1 text-left outline-none transition-colors duration-200 ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
          style={{ background: activeSelected ? 'var(--color-panel)' : 'transparent' }}
        >
          {/* Viewport recortado: durante a troca, o sensor que sai e o que
              entra ficam absolutos aqui dentro, deslizando (push). Fora da
              transição, só o ativo ocupa o inset-0. */}
          <div className="relative min-h-0 w-full flex-1 overflow-hidden">
            {transitioning && leavingIndex != null && (
              <AreaSensorReadout
                key={`leave-${group.sensors[leavingIndex].sensor_code}`}
                {...readoutProps(leavingIndex)}
                className="absolute inset-0"
                style={{ animation: `push-leave ${carouselTransitionMs}ms var(--ease-out-soft) both` }}
              />
            )}
            <AreaSensorReadout
              key={`active-${activeSensor.sensor_code}`}
              {...readoutProps(activeIndex)}
              className="absolute inset-0"
              style={transitioning ? { animation: `push-enter ${carouselTransitionMs}ms var(--ease-out-soft) both` } : undefined}
            />
          </div>
        </button>
      </div>

      {/* Unidade no rodapé, canto inferior direito — FORA do valor medido pelo
          fit, para o fit medir só o número (tamanho consistente entre sensores
          de unidades de comprimentos diferentes, ex. "Pa" vs "%UR"). Reflete o
          sensor ativo. pointer-events-none: é só rótulo. */}
      {activeSensor.unidade && (
        <span
          className="pointer-events-none absolute bottom-3 right-4 font-medium leading-none text-[clamp(0.7rem,3.2cqmin,1.05rem)]"
          style={{ color: 'var(--color-muted)', opacity: valueOpacityFor(activeFreshness) }}
        >
          {activeSensor.unidade}
        </span>
      )}
    </div>
  )
}
