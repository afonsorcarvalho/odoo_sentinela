import type { LiveApi } from '../contracts'
import type { AlarmState, LivePoint, Threshold } from '../../types'
import { TOKEN_STORAGE_KEY } from '../../useAuth'
import { computeStatus } from '../../status'
import { BASE_URL } from './http'
import { realMetaApi } from './metaApi'

// EventSource compartilhado por toda a app: browsers limitam a 6 conexoes
// HTTP/1.1 persistentes por origem, e o dashboard fundido pode ter dezenas
// de sensores visiveis ao mesmo tempo (grid de areas + painel de detalhe) --
// 1 EventSource por sensor estoura esse limite e sensores alem do 6o nunca
// recebem dado (achado em teste real com 12 sensores). Aqui, 1 conexao so
// pro endpoint /live (multiplexado, ver api/live.py), demuxada por
// sensor_id pros callbacks inscritos. Reference-counting: a conexao só
// fecha quando o ultimo inscrito sai.
let sharedSource: EventSource | null = null
const subscribers = new Map<string, Set<(p: LivePoint) => void>>()
const thresholdCache = new Map<string, Threshold | null>()

function ensureSharedSource(): EventSource {
  if (sharedSource) return sharedSource

  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  const es = new EventSource(`${BASE_URL}/live?token=${token}`)
  es.onmessage = (event) => {
    const { sensor_id, time, valor } = JSON.parse(event.data)
    const callbacks = subscribers.get(sensor_id)
    if (!callbacks || callbacks.size === 0) return
    const threshold = thresholdCache.get(sensor_id) ?? null
    const { state } = computeStatus(valor, threshold)
    const alarm_state: AlarmState = state === 'unknown' ? 'ok' : state
    const point: LivePoint = { sensor_code: sensor_id, ts: time, value: valor, alarm_state }
    callbacks.forEach((cb) => cb(point))
  }
  sharedSource = es
  return es
}

function closeSharedSourceIfIdle(): void {
  const totalSubscribers = [...subscribers.values()].reduce((acc, set) => acc + set.size, 0)
  if (totalSubscribers === 0 && sharedSource) {
    sharedSource.close()
    sharedSource = null
  }
}

export const realLiveApi: LiveApi = {
  subscribe(sensor_code, cb) {
    ensureSharedSource()

    if (sensor_code === '') {
      return () => closeSharedSourceIfIdle()
    }

    if (!thresholdCache.has(sensor_code)) {
      realMetaApi.getThreshold(sensor_code)
        .then((t) => thresholdCache.set(sensor_code, t))
        .catch(() => thresholdCache.set(sensor_code, null))
    }

    const callbacks = subscribers.get(sensor_code) ?? new Set()
    callbacks.add(cb)
    subscribers.set(sensor_code, callbacks)

    return () => {
      callbacks.delete(cb)
      if (callbacks.size === 0) subscribers.delete(sensor_code)
      closeSharedSourceIfIdle()
    }
  },
}
