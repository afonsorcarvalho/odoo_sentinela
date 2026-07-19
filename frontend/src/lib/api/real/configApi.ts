import type { ConfigApi } from '../contracts'
import { authFetchJson } from './http'

export const realConfigApi: ConfigApi = {
  getConfig() {
    return authFetchJson('/config')
  },
}
