import type { StatusLeitura, Threshold } from './types'

export type StatusResult = {
  state: 'ok' | 'warn' | 'crit' | 'unknown' | 'fault' | 'invalid'
  label: string
  position: number | null
}

export const LABELS = {
  ok: 'OK',
  warn: 'Perto do limite',
  crit: 'Fora',
  unknown: 'Não avaliado',
  fault: 'Sensor desconectado',
  invalid: 'Leitura inválida',
} as const

// Rótulo de fault depende da causa: laço aberto/fora do envelope NAMUR vs
// coletor sem resposta.
export const SEM_COMUNICACAO = 'Sem comunicação'

export function stateLabel(state: StatusResult['state'], statusLeitura?: StatusLeitura): string {
  if (state === 'fault' && statusLeitura === 'sensor_offline') return SEM_COMUNICACAO
  return LABELS[state]
}

// Margem de "perto do limite": 10% da largura da faixa em cada borda.
export const WARN_MARGIN = 0.1

export function computeStatus(value: number, t: Threshold | null): StatusResult {
  if (!t) return { state: 'unknown', label: LABELS.unknown, position: null }
  const range = t.limite_max - t.limite_min
  const raw = range > 0 ? (value - t.limite_min) / range : 0.5
  const position = Math.min(1, Math.max(0, raw))
  let state: StatusResult['state']
  if (value < t.limite_min || value > t.limite_max) state = 'crit'
  else if (raw <= WARN_MARGIN || raw >= 1 - WARN_MARGIN) state = 'warn'
  else state = 'ok'
  return { state, label: LABELS[state], position }
}

// UNICO lugar da precedencia: o status da leitura (vindo da borda) vence o
// limite. Um valor de instrumento em falha nunca e comparado com a faixa --
// -25 ppm de laço aberto NAO e "OK" so porque cai dentro do limite. Sem
// limite configurado, leitura valida e 'unknown' ("Não avaliado"), nunca 'ok'.
export function resolveStatus(
  value: number | null,
  statusLeitura: StatusLeitura | undefined,
  t: Threshold | null,
): StatusResult {
  if (statusLeitura === 'falha_sensor' || statusLeitura === 'sensor_offline')
    return { state: 'fault', label: stateLabel('fault', statusLeitura), position: null }
  if (statusLeitura === 'suspeito' || statusLeitura === 'erro_leitura')
    return { state: 'invalid', label: LABELS.invalid, position: null }
  if (value === null) return { state: 'unknown', label: LABELS.unknown, position: null }
  return computeStatus(value, t)
}
