import type { MetaApi, HistoryApi, LiveApi } from './contracts'
import { mockMetaApi } from './mock/metaApi'
import { mockHistoryApi } from './mock/historyApi'
import { mockLiveApi } from './mock/liveApi'

// Fase 3 (real) entra aqui sem tocar componentes: trocar por impl HTTP/SSE quando VITE_API_MODE=real.
const mode = import.meta.env.VITE_API_MODE ?? 'mock'
if (mode !== 'mock') console.warn(`VITE_API_MODE=${mode} sem impl real ainda; usando mock`)

export const metaApi: MetaApi = mockMetaApi
export const historyApi: HistoryApi = mockHistoryApi
export const liveApi: LiveApi = mockLiveApi
