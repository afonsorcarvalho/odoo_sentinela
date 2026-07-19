import type { ConfigApi } from '../contracts'
import type { DashboardLayout } from '../../layout/schema'
import { authFetchJson, authFetchJsonWrite } from './http'

export const realConfigApi: ConfigApi = {
  getConfig() {
    return authFetchJson('/config')
  },
  saveLayout(layout: DashboardLayout) {
    return authFetchJsonWrite('/config/layout', 'PUT', { layout })
  },
}
