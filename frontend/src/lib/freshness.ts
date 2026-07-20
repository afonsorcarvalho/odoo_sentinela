import type { LivePoint } from './types'

// Defaults hardcoded nesta fase (ver design doc A2, "Fora de escopo": ficam
// configuraveis via DashboardConfig em fase futura, ao lado de
// carousel_interval_ms). Palpites razoaveis dado que a cadencia real de
// reporte e ~1/min por sensor (bem abaixo de staleMs) -- ver doc, secao
// "Tiers de frescor e thresholds".
export const DEFAULT_STALE_MS = 5 * 60_000
export const DEFAULT_OFFLINE_MS = 15 * 60_000

export type FreshnessTier = 'fresh' | 'stale' | 'offline' | 'never'

export type FreshnessConfig = {
  staleMs?: number
  offlineMs?: number
}

// Pura, sem React: classifica a idade do ultimo LivePoint em tiers. `now" e
// SEMPRE injetado pelo chamador (useNow no caminho real, valor fixo em
// teste) -- nunca Date.now() aqui dentro, para manter isto 100% testavel e
// deterministico.
//
// Fronteiras deterministicas (ver design doc): ageMs === staleMs cai em
// 'fresh' (usa <=), ageMs === offlineMs cai em 'stale' (usa <=). So depois
// de estritamente ultrapassar o limite e que o tier escala.
export function freshness(live: LivePoint | undefined, now: number, cfg?: FreshnessConfig): FreshnessTier {
  if (!live) return 'never'

  const staleMs = cfg?.staleMs ?? DEFAULT_STALE_MS
  const offlineMs = cfg?.offlineMs ?? DEFAULT_OFFLINE_MS
  const ageMs = now - live.ts

  if (ageMs <= staleMs) return 'fresh'
  if (ageMs <= offlineMs) return 'stale'
  return 'offline'
}

// pt-BR, granularidade em minutos (a escala em que fresh->stale->offline
// cruza). Segundos so aparecem abaixo de 1 min -- caminho raro na pratica,
// pois abaixo de 1 min o tier e sempre 'fresh' e nao mostra badge de idade.
export function formatAge(ageMs: number): string {
  const totalMinutes = Math.floor(ageMs / 60_000)

  if (totalMinutes < 1) {
    const seconds = Math.max(0, Math.round(ageMs / 1000))
    return `há ${seconds} s`
  }

  if (totalMinutes < 60) return `há ${totalMinutes} min`

  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return minutes > 0 ? `há ${hours} h ${minutes} min` : `há ${hours} h`
}
