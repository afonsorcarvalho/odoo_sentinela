import type { MetaApi, HistoryApi, LiveApi, AuthApi, AlarmApi, ConfigApi } from './contracts'
import { mockMetaApi } from './mock/metaApi'
import { mockHistoryApi } from './mock/historyApi'
import { mockLiveApi } from './mock/liveApi'
import { mockAuthApi } from './mock/authApi'
import { mockAlarmApi } from './mock/alarmApi'
import { mockConfigApi } from './mock/configApi'
import { realAuthApi } from './real/authApi'
import { realMetaApi } from './real/metaApi'
import { realHistoryApi } from './real/historyApi'
import { realLiveApi } from './real/liveApi'
import { realAlarmApi } from './real/alarmApi'
import { realConfigApi } from './real/configApi'

const mode = import.meta.env.VITE_API_MODE ?? 'mock'
if (mode !== 'real' && mode !== 'mock') {
  console.warn(`VITE_API_MODE=${mode} nao reconhecido; usando mock para todos os adapters`)
}

const useReal = mode === 'real'

export const authApi: AuthApi = useReal ? realAuthApi : mockAuthApi
export const metaApi: MetaApi = useReal ? realMetaApi : mockMetaApi
export const historyApi: HistoryApi = useReal ? realHistoryApi : mockHistoryApi
export const liveApi: LiveApi = useReal ? realLiveApi : mockLiveApi
export const alarmApi: AlarmApi = useReal ? realAlarmApi : mockAlarmApi
export const configApi: ConfigApi = useReal ? realConfigApi : mockConfigApi
