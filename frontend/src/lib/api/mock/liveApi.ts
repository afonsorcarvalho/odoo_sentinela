import type { LiveApi } from '../contracts'
import type { LivePoint } from '../../types'
import { THRESHOLD } from './fixtures'
import { computeStatus } from '../../status'

const TICK_MS = 1000

export const mockLiveApi: LiveApi = {
  subscribe(sensor_code, cb) {
    const mid = (THRESHOLD.limite_min + THRESHOLD.limite_max) / 2
    const amp = (THRESHOLD.limite_max - THRESHOLD.limite_min) / 2.2
    let i = 0
    let ts = 1_700_000_000_000
    const id = setInterval(() => {
      ts += TICK_MS
      const value = +(mid + amp * Math.sin(i / 6)).toFixed(2)
      i++
      const state = computeStatus(value, THRESHOLD).state
      const alarm_state = state === 'unknown' ? 'ok' : state
      const point: LivePoint = { sensor_code, ts, value, alarm_state }
      cb(point)
    }, TICK_MS)
    return () => clearInterval(id)
  },
}
