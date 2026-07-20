import type { LiveApi } from '../contracts'
import type { LivePoint } from '../../types'
import { THRESHOLDS } from './fixtures'
import { computeStatus } from '../../status'

const TICK_MS = 1000

// Amplitude como fracao da faixa do threshold. Expurgo mantem o comportamento
// existente (fica confortavelmente dentro da faixa, sem alteracao observavel).
// Preparo usa amplitude maior, propositalmente: cruza a faixa periodicamente e
// produz 'crit' de vez em quando — a Overview usa isto pra ter uma area com
// alarme ativo pra mostrar (nao seria possivel demonstrar a badge de contagem
// se todo sensor mockado ficasse sempre dentro da faixa).
const AMP_FRACTION: Record<string, number> = {
  'TEMP-EXP-01': 1 / 2.2,
  'TEMP-PRE-01': 1 / 1.4,
}
const DEFAULT_AMP_FRACTION = 1 / 2.2

// Sensor sem threshold (Arsenal): nao ha faixa da qual derivar ponto medio ou
// amplitude — usa uma leitura ambiente plausivel, fixa.
const NO_THRESHOLD_MID = 24
const NO_THRESHOLD_AMP = 3

export const mockLiveApi: LiveApi = {
  subscribe(sensor_code, cb) {
    const threshold = THRESHOLDS[sensor_code] ?? null
    const mid = threshold ? (threshold.limite_min + threshold.limite_max) / 2 : NO_THRESHOLD_MID
    const amp = threshold
      ? (threshold.limite_max - threshold.limite_min) * (AMP_FRACTION[sensor_code] ?? DEFAULT_AMP_FRACTION)
      : NO_THRESHOLD_AMP
    let i = 0
    let ts = 1_700_000_000_000
    const id = setInterval(() => {
      ts += TICK_MS
      const value = +(mid + amp * Math.sin(i / 6)).toFixed(2)
      i++
      const state = computeStatus(value, threshold).state
      const alarm_state = state === 'unknown' ? 'ok' : state
      const point: LivePoint = { sensor_code, ts, value, alarm_state }
      cb(point)
    }, TICK_MS)
    return () => clearInterval(id)
  },

  // Mock nao tem EventSource/rede: reporta 'live' uma vez na inscricao e
  // nunca transiciona -- preserva o seam mock<->real (UI sempre agnostica).
  subscribeConnection(cb) {
    cb('live')
    return () => {}
  },
}
