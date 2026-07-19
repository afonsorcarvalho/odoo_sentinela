import type { ConfigApi } from '../contracts'

export const mockConfigApi: ConfigApi = {
  async getConfig() {
    return { carousel_interval_ms: 3000 }
  },
}
