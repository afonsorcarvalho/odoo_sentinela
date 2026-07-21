import { useLayoutEffect, useRef } from 'react'
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
  // Marcador de offline no cabecalho: distingue "warn/crit por offline" de
  // "warn por valor perto do limite" (ver design doc, "Marcador distinto no
  // nivel da area"). Nao restrito a aggregate==='warn' de proposito: um
  // sensor offline e sempre informacao acionavel p/ o operador, mesmo que a
  // area ja esteja 'crit' por outro motivo (crit nao e rebaixado por
  // offline -- areaAggregateState so escala p/ >= warn).
  const anyOffline = perSensor.some((p) => p.freshness === 'offline')
  const carousel = useSensorCarousel(group.sensors.length, carouselIntervalMs)
  const reducedMotion = usePrefersReducedMotion()
  const activeSensor = group.sensors[carousel.activeIndex] ?? group.sensors[0]
  const activeState = sensorDisplayState(
    thresholdsByCode[activeSensor.sensor_code] ?? null,
    liveByCode[activeSensor.sensor_code],
  )
  const activeLive = liveByCode[activeSensor.sensor_code]
  const activeSelected = activeSensor.sensor_code === selectedSensorCode
  // Freshness efetivo (ja com a escalada never->offline pos-graca) do sensor
  // ATIVO -- mesmo indice de perSensor, pois ambos vem de group.sensors.map
  // na mesma ordem (ver useSensorCarousel: activeIndex indexa group.sensors).
  const activeFreshness: FreshnessTier = perSensor[carousel.activeIndex]?.freshness ?? 'never'
  const activeAgeMs = activeLive ? now - activeLive.ts : undefined
  // offline (real ou escalado de never) faz o StatusDot refletir o estado da
  // CONEXAO, nao mais o alarm_state antigo do ultimo valor conhecido (ver
  // doc, secao Visual, tier 'offline').
  const dotState = activeFreshness === 'offline' ? 'crit' : activeState
  // Atenuacao do valor: 'stale' fica visivel mas suspeito; 'offline' e
  // substituido por '—' (opcao explicita da doc: "ou substituido por '—'")
  // pois nao deve mais ser lido como leitura atual.
  const valueOpacity = activeFreshness === 'stale' ? 0.55 : activeFreshness === 'offline' ? 0.4 : 1
  // Valor bruto animado: offline vira null (sem count-up; exibe '—'). resetKey
  // = sensor ativo faz o count-up SNAPAR na troca do carrossel (não conta do
  // valor de um sensor até o de outro); entre leituras do MESMO sensor, anima.
  const rawValue = activeFreshness === 'offline' ? null : (activeLive?.value ?? null)
  const animatedValue = useCountUp(rawValue, { resetKey: activeSensor.sensor_code })
  const displayValue = animatedValue != null ? animatedValue.toFixed(1) : '—'
  // O valor escala para preencher a caixa (largura e altura) via useFitText.
  // A UNIDADE fica FORA do texto medido (rodapé do card) — assim o fit mede só
  // o número e o tamanho do valor fica consistente entre sensores da mesma
  // área (unidades de comprimentos diferentes, ex. "Pa" vs "%UR", não mudam
  // mais o tamanho do número). min baixo garante que o número nunca é clipado
  // em cards muito pequenos (2×2). Reajusta quando muda o comprimento do
  // número ou a leitura bruta (key={rawValue} remonta o <span> para o bump).
  const { boxRef, textRef, fit } = useFitText({ min: 9 })
  useLayoutEffect(() => {
    fit()
  }, [fit, rawValue, displayValue.length])

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

      {/* flex-1: preenche a altura restante do card para que áreas com 1
          sensor (sem carrossel) fiquem com a MESMA altura das de vários
          sensores — evita cards curtos e desalinhados do canto de resize.
          items-center: dots (coluna vertical, à esquerda) e valor ficam
          centralizados na mesma linha horizontal. */}
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
                aria-selected={i === carousel.activeIndex}
                aria-label={s.measurement_type.name}
                onClick={() => carousel.setActiveIndex(i)}
                className="size-1.5 rounded-full transition-[background,transform] duration-200 ease-out motion-reduce:transition-none"
                style={{
                  background: i === carousel.activeIndex ? 'var(--color-ink)' : 'var(--color-line)',
                  transform: i === carousel.activeIndex ? 'scale(1.15)' : 'scale(1)',
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
          {/* key={activeSensor.sensor_code}: remonta o conteúdo a cada troca
              de sensor, disparando a keyframe carousel-in (cross-fade +
              subida). Animação condicionada ao hook (nao ao style inline
              puro): style inline vence motion-reduce:animate-none por
              specificity de CSS, entao sob prefers-reduced-motion a unica
              forma de fato desligar a animacao e nao aplicar o style. */}
          <span
            key={activeSensor.sensor_code}
            className="flex h-full w-full min-h-0 flex-col gap-0.5 motion-reduce:animate-none"
            style={{ animation: reducedMotion ? undefined : 'carousel-in var(--dur-base) var(--ease-out-soft)' }}
          >
            {/* Nome do sensor: escala com o card via container-query (cqmin,
                relativo ao @container do AreaCard). O status dot e o badge de
                freshness ficam com tamanho próprio (indicadores). */}
            <span
              className="flex items-center gap-2 font-medium text-[clamp(0.72rem,4.5cqmin,1.15rem)]"
              style={{ color: 'var(--color-muted)' }}
            >
              <span data-testid="sensor-status-dot">
                <StatusDot state={dotState} />
              </span>
              {activeSensor.measurement_type.name}
              {activeFreshness !== 'fresh' && <FreshnessBadge tier={activeFreshness} ageMs={activeAgeMs} />}
            </span>
            {/* Caixa que ocupa a altura restante; o valor é escalado por
                useFitText para preencher largura e altura (com respiro). O
                <span> do valor tem key={rawValue} para reiniciar o bump a cada
                nova leitura. */}
            <div ref={boxRef} className="flex min-h-0 flex-1 items-center overflow-hidden">
              <span
                ref={textRef}
                key={rawValue ?? 'none'}
                className="inline-block whitespace-nowrap font-mono font-bold leading-none tabular-nums motion-reduce:animate-none"
                style={{
                  color: activeState === 'ok' || activeState === 'unknown' ? 'var(--color-ink)' : statusTextColor(activeState),
                  opacity: valueOpacity,
                  animation: reducedMotion ? undefined : 'kpi-bump var(--dur-slow) var(--ease-overshoot)',
                }}
              >
                {displayValue}
              </span>
            </div>
          </span>
        </button>
      </div>

      {/* Unidade no rodapé, canto inferior direito — FORA do valor medido pelo
          fit (ver comentário do useFitText acima), tamanho fixo/modesto que
          escala de leve com o card, sem competir com o número. Reflete o
          sensor ativo do carrossel. pointer-events-none: é só rótulo, não
          rouba o clique de seleção do sensor. */}
      {activeSensor.unidade && (
        <span
          className="pointer-events-none absolute bottom-3 right-4 font-medium leading-none text-[clamp(0.7rem,3.2cqmin,1.05rem)]"
          style={{ color: 'var(--color-muted)', opacity: valueOpacity }}
        >
          {activeSensor.unidade}
        </span>
      )}
    </div>
  )
}
