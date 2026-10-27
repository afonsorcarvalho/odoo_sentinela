import { useLayoutEffect } from 'react'
import { useSensorMeta } from '../../lib/queries'
import { useLiveTail } from '../../lib/useLiveTail'
import { useCountUp } from '../../lib/useCountUp'
import { useFitText } from '../../lib/useFitText'
import { usePrefersReducedMotion } from '../../lib/useSensorCarousel'
import { formatKpi, autoCasas } from '../../lib/kpiFormat'
import { StatusIcon, statusTextColor } from '../statusVisuals'
import { stateLabel } from '../../lib/status'
import { useNow } from '../../lib/useNow'
import { freshness } from '../../lib/freshness'
import { FreshnessBadge } from '../FreshnessBadge'
import type { StatusResult } from '../../lib/status'

type State = StatusResult['state']

// Ranking de severidade para a semântica `max()` do override de threshold:
// quanto maior o índice, mais severo. unknown < ok < invalid < warn < crit = fault.
const SEVERITY_RANK: Record<State, number> = { unknown: 0, ok: 1, invalid: 2, warn: 3, crit: 4, fault: 4 }

function maisSevero(a: State, b: State): State {
  return SEVERITY_RANK[b] > SEVERITY_RANK[a] ? b : a
}

// KPI: valor atual (live) de 1 sensor em destaque, cor por estado de alarme.
// `limiteMin`/`limiteMax` são um override display-only, configurável por widget
// (options do layout): quando o valor ao vivo está fora dessa faixa, ELEVA o
// estado para 'crit'. O override NUNCA rebaixa o alarm_state autoritativo que
// vem do backend — a cor final é sempre o mais severo entre os dois (ver spec
// B2 §KPI — threshold). Sem limiteMin/limiteMax, comportamento idêntico ao
// atual: cor só por alarm_state.
export function KpiWidget({
  sensorCode,
  label,
  limiteMin,
  limiteMax,
  casasDecimais,
  digitosInteiros,
}: {
  sensorCode: string
  label?: string
  limiteMin?: number
  limiteMax?: number
  casasDecimais?: number
  digitosInteiros?: number
}) {
  const meta = useSensorMeta(sensorCode)
  const { last } = useLiveTail(sensorCode)
  const titulo = label ?? meta.data?.name ?? sensorCode
  const unidade = meta.data?.unidade ?? ''
  const estadoBackend: State = last?.alarm_state ?? 'unknown'
  const temOverride = limiteMin != null || limiteMax != null
  // fault/invalid: o valor não é medição -> sem número, sem override de faixa.
  const instrumentoFalho = estadoBackend === 'fault' || estadoBackend === 'invalid'
  const foraDaFaixa =
    temOverride &&
    !instrumentoFalho &&
    last != null &&
    ((limiteMin != null && last.value < limiteMin) || (limiteMax != null && last.value > limiteMax))
  const state: State = foraDaFaixa ? maisSevero(estadoBackend, 'crit') : estadoBackend
  // Frescor: mesma máquina do AreaCard (useNow força reavaliação periódica
  // mesmo sem novo dado, para o tier envelhecer sozinho até 'offline').
  const now = useNow()
  const tier = freshness(last ?? undefined, now)
  const ageMs = last ? now - last.ts : undefined
  // Mesma convenção do AreaCard: ok/unknown usam --color-ink (contraste
  // padrão); apenas warn/crit usam o token de cor de estado. A atenuação por
  // frescor VENCE tudo isso — um número velho não pode gritar 'crit' do
  // override como se fosse leitura atual.
  const cor =
    tier !== 'fresh'
      ? 'var(--color-muted)'
      : state === 'ok' || state === 'unknown' || state === 'invalid'
        ? 'var(--color-ink)'
        : statusTextColor(state)
  const rawValue = instrumentoFalho ? null : (last?.value ?? null)
  const animated = useCountUp(rawValue)
  const reducedMotion = usePrefersReducedMotion()
  // Formatação: casasDecimais/digitosInteiros vêm das options do widget; ausentes
  // caem no auto histórico (casas detectadas do valor bruto, cap 3; sem padding).
  // O auto é derivado de `rawValue` (o alvo fixo), NUNCA de `animated` (frame
  // interpolado do count-up): durante a transição de ~550ms, `animated` é um
  // float ruidoso e autoCasas(animated) injetaria casas decimais espúrias que
  // só se corrigiriam no frame final, quebrando também a estabilidade de
  // comprimento do useFitText.
  const displayValue =
    animated != null
      ? formatKpi(animated, { casasDecimais: casasDecimais ?? autoCasas(rawValue ?? 0), digitosInteiros })
      : '—'

  // O valor escala para preencher a caixa (largura e altura) via useFitText.
  // Reajusta quando: o comprimento do texto muda (mais/menos dígitos — largura
  // depende só disso por tabular-nums) ou a unidade muda; e a cada nova leitura
  // (rawValue), pois o key={rawValue} remonta o <span> para reiniciar o bump e
  // o novo nó precisa ser reajustado. Frames intermediários do count-up com o
  // mesmo comprimento não disparam refit.
  const { boxRef, textRef, fit } = useFitText()
  useLayoutEffect(() => {
    fit()
  }, [fit, rawValue, displayValue.length, unidade])

  return (
    <div
      className="flex h-full flex-col rounded-lg p-3"
      style={{ background: 'var(--color-surface)' }}
    >
      <div className="flex items-center gap-2">
        <p
          className="min-w-0 flex-1 truncate text-xs font-bold uppercase tracking-wide"
          style={{ color: 'var(--color-muted)' }}
        >
          {titulo}
        </p>
        {tier !== 'fresh' && <FreshnessBadge tier={tier} ageMs={ageMs} />}
        {instrumentoFalho && (
          <span
            className="inline-flex shrink-0 items-center gap-1 text-xs font-semibold"
            style={{ color: statusTextColor(state) }}
          >
            <StatusIcon state={state} />
            {stateLabel(state, last?.status_leitura)}
          </span>
        )}
      </div>
      {/* Caixa que ocupa toda a altura restante; o valor é centralizado e
          escalado por useFitText para preencher largura e altura, com uma
          folga proporcional (fillRatio) de respiro em todos os lados. */}
      <div ref={boxRef} className="flex min-h-0 flex-1 items-center justify-center overflow-hidden">
        <span
          ref={textRef}
          key={rawValue ?? 'none'}
          className="inline-block whitespace-nowrap font-bold leading-none tabular-nums motion-reduce:animate-none"
          style={{
            color: cor,
            opacity: tier !== 'fresh' ? 0.7 : undefined,
            animation: reducedMotion ? undefined : 'kpi-bump var(--dur-slow) var(--ease-overshoot)',
          }}
        >
          {displayValue}
          {unidade && (
            <span className="ml-[0.15em] text-[0.5em] font-medium" style={{ color: 'var(--color-muted)' }}>
              {unidade}
            </span>
          )}
        </span>
      </div>
    </div>
  )
}
