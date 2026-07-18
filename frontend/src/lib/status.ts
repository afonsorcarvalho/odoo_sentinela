import type { Threshold } from './types'

export type StatusResult = {
  state: 'ok' | 'warn' | 'crit' | 'unknown'
  label: string
  position: number | null
}

const LABELS = {
  ok: 'Dentro da faixa',
  warn: 'Perto do limite',
  crit: 'Fora da faixa',
  unknown: 'Sem limite',
} as const

// Margem de "perto do limite": 10% da largura da faixa em cada borda.
const WARN_MARGIN = 0.1

export function computeStatus(value: number, t: Threshold | null): StatusResult {
  if (!t) return { state: 'unknown', label: LABELS.unknown, position: null }
  const range = t.limite_max - t.limite_min
  const raw = range > 0 ? (value - t.limite_min) / range : 0.5
  const position = Math.min(1, Math.max(0, raw))
  let state: StatusResult['state']
  if (value < t.limite_min || value > t.limite_max) state = 'crit'
  else if (raw < WARN_MARGIN || raw > 1 - WARN_MARGIN) state = 'warn'
  else state = 'ok'
  return { state, label: LABELS[state], position }
}
