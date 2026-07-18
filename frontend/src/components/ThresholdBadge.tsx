import type { Threshold } from '../lib/types'

export function ThresholdBadge({
  threshold,
  unidade,
}: {
  threshold: Threshold | null
  unidade: string
}) {
  if (!threshold) {
    return (
      <span className="text-sm" style={{ color: 'var(--color-muted)' }}>
        Sem limite configurado
      </span>
    )
  }

  return (
    <div className="flex flex-wrap items-center gap-3 text-sm" style={{ color: 'var(--color-muted)' }}>
      <span>
        Faixa segura:{' '}
        <b className="font-mono tabular-nums" style={{ color: 'var(--color-ink)' }}>
          {threshold.limite_min}–{threshold.limite_max} {unidade}
        </b>
      </span>
      {threshold.is_valor_padrao_regulatorio && (
        <span
          className="rounded px-2 py-0.5 text-xs font-semibold"
          style={{
            background: 'var(--color-panel)',
            // 70% primary / 30% ink: --color-primary puro sobre --color-panel
            // fica em 4.48:1 no tema claro (abaixo do mínimo de 4.5:1).
            // Verificado por script (OKLCH->sRGB completo): a mistura sobe
            // para 6.66:1 claro / 9.15:1 escuro, mesma técnica do
            // TEXT_COLOR de LiveReadout.tsx.
            color: 'color-mix(in oklch, var(--color-primary) 70%, var(--color-ink) 30%)',
          }}
        >
          Padrão RDC 15
        </span>
      )}
    </div>
  )
}
