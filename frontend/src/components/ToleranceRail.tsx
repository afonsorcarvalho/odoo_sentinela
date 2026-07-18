import type { StatusResult } from '../lib/status'
import { WARN_MARGIN } from '../lib/status'

type State = StatusResult['state']

// Cor do ponto: tom pleno do token de estado (elemento gráfico, não texto —
// o contraste textual é garantido pelo rótulo acima, não pela cor sozinha).
const DOT: Record<State, string> = {
  ok: 'var(--color-good)',
  warn: 'var(--color-warn)',
  crit: 'var(--color-crit)',
  unknown: 'var(--color-muted)',
}

function formatTick(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1)
}

export function ToleranceRail({
  position,
  state,
  min,
  max,
  warnMargin = WARN_MARGIN,
}: {
  position: number | null
  state: State
  min?: number
  max?: number
  warnMargin?: number
}) {
  const pct = position === null ? 50 : position * 100
  const bandStart = warnMargin * 100
  const bandEnd = (1 - warnMargin) * 100
  const pinnedLow = state === 'crit' && position === 0
  const pinnedHigh = state === 'crit' && position === 1

  return (
    <div className="w-full">
      <div className="relative h-1.5" aria-hidden>
        {/* trilho */}
        <div
          className="absolute inset-0 rounded-full"
          style={{ background: 'var(--color-line)' }}
        />
        {/* faixa segura (banda entre as margens de alerta) */}
        <div
          className="absolute inset-y-0 rounded-full"
          style={{
            left: `${bandStart}%`,
            right: `${100 - bandEnd}%`,
            background: 'var(--color-good)',
            opacity: 0.2,
          }}
        />
        {/* traços de fim de escala (min / max) */}
        <span
          className="absolute -top-[3px] h-[9px] w-px"
          style={{ left: 0, background: 'var(--color-muted)' }}
        />
        <span
          className="absolute -top-[3px] h-[9px] w-px"
          style={{ left: '100%', background: 'var(--color-muted)' }}
        />
        {/* indicador fora de escala (pino no limite, valor além do traço) */}
        {pinnedLow && (
          <span
            className="absolute top-1/2 -translate-y-1/2 border-y-[4px] border-r-[6px] border-y-transparent"
            style={{ left: -6, borderRightColor: DOT.crit }}
          />
        )}
        {pinnedHigh && (
          <span
            className="absolute top-1/2 -translate-y-1/2 border-y-[4px] border-l-[6px] border-y-transparent"
            style={{ right: -6, borderLeftColor: DOT.crit }}
          />
        )}
        {/* ponto — posição codifica o valor dentro da faixa */}
        {position !== null && (
          <div
            className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full transition-[left] duration-200 ease-out motion-reduce:transition-none"
            style={{
              left: `${pct}%`,
              background: DOT[state],
              boxShadow: '0 0 0 2px var(--color-surface), 0 0 0 3px var(--color-line)',
            }}
          />
        )}
      </div>
      {(min !== undefined || max !== undefined) && (
        <div
          className="mt-1.5 flex justify-between font-mono text-[11px] tabular-nums"
          style={{ color: 'var(--color-muted)' }}
          aria-hidden
        >
          <span>{min !== undefined ? formatTick(min) : ''}</span>
          <span>{max !== undefined ? formatTick(max) : ''}</span>
        </div>
      )}
    </div>
  )
}
