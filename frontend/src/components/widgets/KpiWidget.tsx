import { useSensorMeta } from '../../lib/queries'
import { useLiveTail } from '../../lib/useLiveTail'
import { useCountUp } from '../../lib/useCountUp'
import { usePrefersReducedMotion } from '../../lib/useSensorCarousel'
import { statusTextColor } from '../statusVisuals'
import type { StatusResult } from '../../lib/status'

type State = StatusResult['state']

// Ranking de severidade para a semântica `max()` do override de threshold:
// quanto maior o índice, mais severo. unknown < ok < warn < crit.
const SEVERITY_RANK: Record<State, number> = { unknown: 0, ok: 1, warn: 2, crit: 3 }

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
}: {
  sensorCode: string
  label?: string
  limiteMin?: number
  limiteMax?: number
}) {
  const meta = useSensorMeta(sensorCode)
  const { last } = useLiveTail(sensorCode)
  const titulo = label ?? meta.data?.name ?? sensorCode
  const unidade = meta.data?.unidade ?? ''
  const estadoBackend: State = last?.alarm_state ?? 'unknown'
  const temOverride = limiteMin != null || limiteMax != null
  const foraDaFaixa =
    temOverride &&
    last != null &&
    ((limiteMin != null && last.value < limiteMin) || (limiteMax != null && last.value > limiteMax))
  const state: State = foraDaFaixa ? maisSevero(estadoBackend, 'crit') : estadoBackend
  // Mesma convenção do AreaCard: ok/unknown usam --color-ink (contraste
  // padrão); apenas warn/crit usam o token de cor de estado.
  const cor = state === 'ok' || state === 'unknown' ? 'var(--color-ink)' : statusTextColor(state)
  const rawValue = last?.value ?? null
  const animated = useCountUp(rawValue)
  const reducedMotion = usePrefersReducedMotion()
  // Preserva as casas decimais do valor bruto durante a interpolação.
  const casas = rawValue != null && !Number.isInteger(rawValue) ? Math.min(String(rawValue).split('.')[1]?.length ?? 1, 3) : 0
  const displayValue = animated != null ? animated.toFixed(casas) : '—'

  return (
    <div
      className="flex h-full flex-col justify-between rounded-lg p-3"
      style={{ background: 'var(--color-surface)' }}
    >
      <p
        className="truncate text-xs font-bold uppercase tracking-wide"
        style={{ color: 'var(--color-muted)' }}
      >
        {titulo}
      </p>
      <div className="flex items-baseline gap-1">
        {/* Fonte fluida via container query: escala com a largura do card
            (WidgetFrame e @container), nao da viewport. */}
        <span
          key={rawValue ?? 'none'}
          className="font-bold tabular-nums text-[clamp(1.25rem,8cqw,2.25rem)] motion-reduce:animate-none"
          style={{
            color: cor,
            animation: reducedMotion ? undefined : 'kpi-bump var(--dur-slow) var(--ease-overshoot)',
          }}
        >
          {displayValue}
        </span>
        <span className="text-sm" style={{ color: 'var(--color-muted)' }}>
          {unidade}
        </span>
      </div>
    </div>
  )
}
