import type { MetaApi, HistoryApi, LiveApi, AuthApi } from './contracts'
import { mockMetaApi } from './mock/metaApi'
import { mockHistoryApi } from './mock/historyApi'
import { mockLiveApi } from './mock/liveApi'
import { mockAuthApi } from './mock/authApi'
import { realAuthApi } from './real/authApi'

// Fase 3 (real) entra aqui sem tocar componentes: authApi ja tem impl real
// (ver frontend/CONTRACTS.md §5) -- metaApi/historyApi/liveApi ainda nao.
const mode = import.meta.env.VITE_API_MODE ?? 'mock'
if (mode !== 'mock') {
  console.info(
    `VITE_API_MODE=${mode}: authApi real; metaApi/historyApi/liveApi ainda mock (adapters reais nao implementados nesta fatia)`,
  )
}

export const authApi: AuthApi = mode === 'real' ? realAuthApi : mockAuthApi
export const metaApi: MetaApi = mockMetaApi
export const historyApi: HistoryApi = mockHistoryApi
export const liveApi: LiveApi = mockLiveApi
