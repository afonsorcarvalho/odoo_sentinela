import type { LiveApi } from '../contracts'
import type { LivePoint, Threshold } from '../../types'
import { computeStatus } from '../../status'
import { realMetaApi } from './metaApi'
import { realHistoryApi } from './historyApi'

const POLL_MS = 3000

export const realLiveApi: LiveApi = {
  subscribe(sensor_code, cb) {
    let cancelled = false
    let threshold: Threshold | null = null
    realMetaApi.getThreshold(sensor_code).then((t) => { threshold = t })

    const tick = async () => {
      const history = await realHistoryApi.getHistory(sensor_code, '1h')
      const last = history.points[history.points.length - 1]
      if (!last || cancelled) return
      const value = 'value' in last ? last.value : last.avg
      const state = computeStatus(value, threshold).state
      const alarm_state = state === 'unknown' ? 'ok' : state
      cb({ sensor_code, ts: last.ts, value, alarm_state } satisfies LivePoint)
    }

    tick()
    const id = setInterval(tick, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  },
}
