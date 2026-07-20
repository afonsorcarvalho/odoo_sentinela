import { formatAge, type FreshnessTier } from '../lib/freshness'

// Badge de frescor exibido ao lado do nome do sensor ATIVO no AreaCard.
// So faz sentido para os tiers que precisam de sinal alem do valor bruto --
// 'fresh' nao renderiza nada (e o comportamento de antes da feature A2:
// quem chama nem deve montar este componente nesse caso).
export type FreshnessBadgeTier = Exclude<FreshnessTier, 'fresh'>

const COLOR: Record<FreshnessBadgeTier, string> = {
  stale: 'var(--color-warn)',
  offline: 'var(--color-crit)',
  never: 'var(--color-muted)',
}

export function FreshnessBadge({ tier, ageMs }: { tier: FreshnessBadgeTier; ageMs?: number }) {
  const label = tier === 'never' ? 'aguardando dado' : ageMs !== undefined ? formatAge(ageMs) : 'offline'

  return (
    <span
      data-testid="freshness-badge"
      className="inline-flex items-center gap-1 text-xs font-medium"
      style={{ color: COLOR[tier] }}
    >
      {tier === 'stale' && <ClockIcon />}
      {tier === 'offline' && <DisconnectIcon />}
      {label}
    </span>
  )
}

// Relogio: sinaliza "isto envelheceu" (tier stale).
function ClockIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      aria-hidden="true"
    >
      <circle cx="8" cy="8" r="6.2" />
      <path d="M8 4.6V8.2L10.4 9.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// Desconexao: sinaliza "sensor parado" (tier offline). Reusado tambem no
// marcador de cabecalho da area (AreaCard).
export function DisconnectIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      aria-hidden="true"
    >
      <path d="M3 6.5A6.6 6.6 0 0 1 8 4.5m5 2A6.6 6.6 0 0 0 8 4.5" strokeLinecap="round" />
      <path d="M5.2 9A3.6 3.6 0 0 1 8 7.7m2.8 1.3A3.6 3.6 0 0 0 8 7.7" strokeLinecap="round" />
      <circle cx="8" cy="11.6" r="0.9" fill="currentColor" stroke="none" />
      <path d="M2.2 2.2 13.8 13.8" strokeLinecap="round" />
    </svg>
  )
}
