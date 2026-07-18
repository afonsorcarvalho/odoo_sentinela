import { computeStatus, LABELS, type StatusResult } from '../lib/status'
import type { Threshold, AlarmState } from '../lib/types'
import { ToleranceRail } from './ToleranceRail'

type State = StatusResult['state']

// Cor de texto/ícone derivada do token de estado, misturada com --color-ink
// para garantir >=4.5:1 de contraste em ambos os temas (o token puro de
// warn/good sozinho não passa em WCAG AA sobre a superfície clara).
// Proporção 60/40 verificada por script (conversão OKLCH->sRGB completa,
// incluindo interpolação de matiz) contra --color-surface nos dois temas;
// pior caso é warn no tema claro, com contraste ~5.7:1 (margem sobre 4.5:1).
const TEXT_COLOR: Record<State, string> = {
  ok: 'color-mix(in oklch, var(--color-good) 60%, var(--color-ink) 40%)',
  warn: 'color-mix(in oklch, var(--color-warn) 60%, var(--color-ink) 40%)',
  crit: 'color-mix(in oklch, var(--color-crit) 60%, var(--color-ink) 40%)',
  unknown: 'var(--color-muted)',
}

function StatusIcon({ state }: { state: State }) {
  const common = { width: 14, height: 14, viewBox: '0 0 16 16', fill: 'currentColor' }
  switch (state) {
    case 'ok':
      return (
        <svg {...common} aria-hidden="true">
          <circle cx="8" cy="8" r="6" />
        </svg>
      )
    case 'warn':
      return (
        <svg {...common} aria-hidden="true">
          <path d="M8 1.6 15 14.4H1L8 1.6Z" />
        </svg>
      )
    case 'crit':
      return (
        <svg {...common} aria-hidden="true">
          <rect x="2.2" y="2.2" width="11.6" height="11.6" rx="2" />
        </svg>
      )
    case 'unknown':
      return (
        <svg {...common} fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
          <circle cx="8" cy="8" r="5.6" strokeDasharray="2.4 2.4" />
        </svg>
      )
  }
}

export function LiveReadout({
  value,
  unidade,
  threshold,
  state,
}: {
  value: number | null
  unidade: string
  threshold: Threshold | null
  state?: AlarmState
}) {
  const derived: StatusResult =
    value !== null
      ? computeStatus(value, threshold)
      : { state: 'unknown', label: LABELS.unknown, position: null }
  const st: State = state ?? derived.state

  return (
    <div
      className="rounded-2xl p-6 md:p-7"
      style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}
    >
      <div className="flex items-end gap-2">
        <span
          className="font-mono text-5xl font-semibold leading-none tracking-tight tabular-nums transition-colors duration-200 ease-out motion-reduce:transition-none md:text-6xl"
          style={{ color: 'var(--color-ink)' }}
        >
          {value === null ? '—' : value.toFixed(1)}
        </span>
        <span
          className="pb-1 text-lg font-medium uppercase tracking-wide md:text-xl"
          style={{ color: 'var(--color-muted)' }}
        >
          {unidade}
        </span>
      </div>

      <div
        className="mt-4 flex items-center gap-2 text-sm font-semibold transition-colors duration-200 ease-out motion-reduce:transition-none"
        style={{ color: TEXT_COLOR[st] }}
      >
        <StatusIcon state={st} />
        <span>{LABELS[st]}</span>
      </div>

      <div className="mt-5">
        <ToleranceRail
          position={derived.position}
          state={st}
          min={threshold?.limite_min}
          max={threshold?.limite_max}
        />
      </div>
    </div>
  )
}
