import type { HistoryApi } from '../contracts'
import { authFetchJson } from './http'

export const realHistoryApi: HistoryApi = {
  getHistory(code, window) {
    return authFetchJson(`/sensores/${code}/historico?window=${window}`)
  },
}
