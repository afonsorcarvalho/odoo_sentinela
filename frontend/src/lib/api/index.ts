import type { MetaApi, HistoryApi, LiveApi, AuthApi } from './contracts'
import { mockMetaApi } from './mock/metaApi'
import { mockHistoryApi } from './mock/historyApi'
import { mockLiveApi } from './mock/liveApi'
import { mockAuthApi } from './mock/authApi'
import { realAuthApi } from './real/authApi'
import { realMetaApi } from './real/metaApi'
import { realHistoryApi } from './real/historyApi'

// Fase 3 (real) entra aqui sem tocar componentes: authApi/metaApi/historyApi
// ja tem impl real (ver frontend/CONTRACTS.md) -- liveApi ainda nao (sem
// backend SSE).
const mode = import.meta.env.VITE_API_MODE ?? 'mock'
if (mode === 'real') {
  console.info(
    'VITE_API_MODE=real: authApi/metaApi/historyApi reais; liveApi ainda mock (sem backend SSE)',
  )
} else if (mode !== 'mock') {
  console.warn(`VITE_API_MODE=${mode} nao reconhecido; usando mock para todos os adapters`)
}

export const authApi: AuthApi = mode === 'real' ? realAuthApi : mockAuthApi
export const metaApi: MetaApi = mode === 'real' ? realMetaApi : mockMetaApi
export const historyApi: HistoryApi = mode === 'real' ? realHistoryApi : mockHistoryApi
export const liveApi: LiveApi = mockLiveApi
