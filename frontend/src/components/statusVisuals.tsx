import type { StatusResult } from '../lib/status'

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
  fault: 'color-mix(in oklch, var(--color-crit) 60%, var(--color-ink) 40%)',
  invalid: 'var(--color-muted)',
}

export function statusTextColor(state: State): string {
  return TEXT_COLOR[state]
}

export function StatusIcon({ state }: { state: State }) {
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
    case 'fault':
      // Quadrado VAZADO com X: mesma família de severidade de crit (quadrado),
      // mas forma distinta -- "não sei o valor", não "valor fora".
      return (
        <svg {...common} fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
          <rect x="2.6" y="2.6" width="10.8" height="10.8" rx="1.6" />
          <path d="M5.5 5.5l5 5M10.5 5.5l-5 5" strokeLinecap="round" />
        </svg>
      )
    case 'invalid':
      // Losango tracejado neutro: leitura recebida mas não confiável.
      return (
        <svg {...common} fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
          <path d="M8 1.8 14.2 8 8 14.2 1.8 8Z" strokeDasharray="2.4 2.4" />
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
