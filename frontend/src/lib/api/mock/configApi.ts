import type { ConfigApi } from '../contracts'

export const mockConfigApi: ConfigApi = {
  async getConfig() {
    // Valor deliberadamente diferente do fallback hardcoded (3000) em
    // DashboardPage.tsx e do default do AreaCard: prova que o valor flui
    // do mock/API ate o componente renderizado, e nao e uma coincidencia
    // mascarada pelo `?? 3000`.
    return { carousel_interval_ms: 4000 }
  },
}
