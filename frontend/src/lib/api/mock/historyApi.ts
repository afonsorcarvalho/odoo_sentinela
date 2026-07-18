import type { HistoryApi } from '../contracts'
import type { HistoryResponse, HistoryPoint, Window } from '../../types'
import { THRESHOLD } from './fixtures'

const SPAN_MS: Record<Window, number> = {
  '1h': 3_600_000, '24h': 86_400_000, '7d': 604_800_000, '30d': 2_592_000_000,
}

// Série sintética determinística (senoide em torno do meio da faixa + ruído fixo).
function synth(window: Window): { resolution: 'raw' | 'agg'; points: HistoryPoint[] } {
  const span = SPAN_MS[window]
  const now = 1_700_000_000_000 // base fixa (sem Date.now — determinístico p/ teste)
  const mid = (THRESHOLD.limite_min + THRESHOLD.limite_max) / 2
  const amp = (THRESHOLD.limite_max - THRESHOLD.limite_min) / 3
  const n = window === '1h' ? 240 : 720
  const step = span / n
  const raw = window === '1h'
  const points: HistoryPoint[] = []
  for (let i = 0; i < n; i++) {
    const ts = now - span + i * step
    const base = mid + amp * Math.sin(i / 12)
    if (raw) points.push({ ts, value: +base.toFixed(2) })
    else points.push({ ts, min: +(base - amp / 4).toFixed(2), max: +(base + amp / 4).toFixed(2), avg: +base.toFixed(2) })
  }
  return { resolution: raw ? 'raw' : 'agg', points }
}

export const mockHistoryApi: HistoryApi = {
  async getHistory(sensor_code: string, window: Window): Promise<HistoryResponse> {
    const { resolution, points } = synth(window)
    return { sensor_code, window, resolution, points }
  },
}
