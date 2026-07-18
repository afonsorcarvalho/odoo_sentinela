import type { MetaApi } from '../contracts'
import { authFetchJson } from './http'

export const realMetaApi: MetaApi = {
  getSensor(code) {
    return authFetchJson(`/sensores/${code}`)
  },
  getThreshold(code) {
    return authFetchJson(`/sensores/${code}/threshold`)
  },
  listSensors() {
    return authFetchJson('/sensores')
  },
}
