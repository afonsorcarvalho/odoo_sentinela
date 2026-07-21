import type { ConfigApi } from '../contracts'
import type { DashboardLayout } from '../../layout/schema'

// Estado em memória: prova o round-trip save→get no modo mock.
let _layout: DashboardLayout | null = null

export const mockConfigApi: ConfigApi = {
  async getConfig() {
    // Valor deliberadamente diferente do fallback hardcoded (3000) em
    // DashboardPage.tsx e do default do AreaCard: prova que o valor flui
    // do mock/API ate o componente renderizado, e nao e uma coincidencia
    // mascarada pelo `?? 3000`.
    return { carousel_interval_ms: 4000, carousel_transition_ms: 500, layout: _layout }
  },
  async saveLayout(layout: DashboardLayout) {
    _layout = layout
    return { layout }
  },
}
