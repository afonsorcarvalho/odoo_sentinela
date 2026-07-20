import type { LiveApi } from '../contracts'
import type { AlarmState, LiveConnectionState, LivePoint, Threshold } from '../../types'
import { TOKEN_STORAGE_KEY } from '../../useAuth'
import { computeStatus } from '../../status'
import { BASE_URL } from './http'
import { realMetaApi } from './metaApi'

// readyState do EventSource nativo -- valores fixos (nao EventSource.CONNECTING/
// .CLOSED) porque em teste o global e substituido por um stub sem esses
// estaticos; ver design doc A3.
const READY_STATE_CONNECTING = 0
const READY_STATE_CLOSED = 2

// Grace de entrada em 'reconnecting': engole blips de rede curtos (< 3s) sem
// piscar o badge. So vale na entrada -- onopen sempre faz snap imediato pra
// 'live', sem debounce de saida.
const RECONNECT_GRACE_MS = 3000

// Estado de conexao e listeners: nivel de modulo (nao dentro de um hook) —
// mesma razao do EventSource ser singleton: 1 fonte da verdade e 1 timer de
// grace, nao um por observador. Otimista no boot (ver design doc A3, "Estado
// inicial"): comeca em 'live' antes de qualquer onopen/onerror real.
let connectionState: LiveConnectionState = 'live'
const connectionListeners = new Set<(s: LiveConnectionState) => void>()
let graceTimer: ReturnType<typeof setTimeout> | null = null

function clearGraceTimer(): void {
  if (graceTimer !== null) {
    clearTimeout(graceTimer)
    graceTimer = null
  }
}

function setConnectionState(next: LiveConnectionState): void {
  if (connectionState === next) return
  connectionState = next
  connectionListeners.forEach((cb) => cb(connectionState))
}

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

  // Nova conexao: otimista, comeca (ou volta a) 'live' -- ver design doc A3,
  // "Estado inicial". Feito aqui (apos o early-return acima), nunca antes
  // dele: um 2o subscribe() no meio da sessao so reusa o source existente e
  // NAO deve resetar um 'reconnecting'/'offline' real de volta pra 'live'.
  clearGraceTimer()
  connectionState = 'live'

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
  es.onopen = () => {
    // Recuperacao e boa noticia: snap imediato, sem esperar/checar grace.
    clearGraceTimer()
    setConnectionState('live')
  }
  es.onerror = () => {
    if (es.readyState === READY_STATE_CLOSED) {
      // Fechamento fatal (ex.: 401 de token expirado) -- o browser NAO tenta
      // de novo sozinho. Terminal nesta fase, ignora o grace (nao e um blip).
      clearGraceTimer()
      setConnectionState('offline')
      return
    }
    if (es.readyState === READY_STATE_CONNECTING) {
      // Erro transitorio -- o browser ja esta tentando reconectar sozinho.
      // Arma o grace SO na entrada (estado atual 'live' e nenhum timer already
      // pendente): sem o guard de graceTimer, onerror repetido durante uma
      // queda real reiniciaria o timer a cada disparo e 'reconnecting' nunca
      // seria alcancado.
      if (connectionState === 'live' && graceTimer === null) {
        graceTimer = setTimeout(() => {
          graceTimer = null
          setConnectionState('reconnecting')
        }, RECONNECT_GRACE_MS)
      }
    }
  }
  sharedSource = es
  return es
}

function closeSharedSourceIfIdle(): void {
  const totalSubscribers = [...subscribers.values()].reduce((acc, set) => acc + set.size, 0)
  if (totalSubscribers === 0 && sharedSource) {
    sharedSource.close()
    sharedSource = null
    clearGraceTimer()
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
      if (subscribers.get(sensor_code) === callbacks && callbacks.size === 0) {
        subscribers.delete(sensor_code)
      }
      closeSharedSourceIfIdle()
    }
  },

  // Observacional: nao abre o EventSource por si so (ver contracts.ts). O
  // badge so reflete a conexao real enquanto algo mais (ex.: useLiveStatuses)
  // mantiver um subscribe() de dados ativo -- e sempre o caso no dashboard.
  subscribeConnection(cb) {
    connectionListeners.add(cb)
    cb(connectionState)
    return () => {
      connectionListeners.delete(cb)
    }
  },
}
