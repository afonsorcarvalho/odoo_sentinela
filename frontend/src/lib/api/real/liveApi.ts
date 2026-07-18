import type { LiveApi } from '../contracts'
import type { AlarmState, Threshold } from '../../types'
import { TOKEN_STORAGE_KEY } from '../../useAuth'
import { computeStatus } from '../../status'
import { BASE_URL } from './http'
import { realMetaApi } from './metaApi'

export const realLiveApi: LiveApi = {
  subscribe(sensor_code, cb) {
    // Sem isso, um `selectedCode` ainda nao resolvido (antes dos sensores
    // carregarem) abre um EventSource pra `/sensores//live` (barra dupla) --
    // achado na verificacao visual do redesign, mesma classe de bug ja
    // corrigida no adapter de polling que esta versao substitui.
    if (sensor_code === '') return () => {}

    let threshold: Threshold | null = null
    realMetaApi.getThreshold(sensor_code).then((t) => { threshold = t }).catch(() => {})

    const token = localStorage.getItem(TOKEN_STORAGE_KEY)
    const es = new EventSource(`${BASE_URL}/sensores/${sensor_code}/live?token=${token}`)
    es.onmessage = (event) => {
      const { time, valor } = JSON.parse(event.data)
      const { state } = computeStatus(valor, threshold)
      const alarm_state: AlarmState = state === 'unknown' ? 'ok' : state
      cb({ sensor_code, ts: time, value: valor, alarm_state })
    }
    return () => es.close()
  },
}
