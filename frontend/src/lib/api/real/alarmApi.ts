import type { AlarmApi } from '../contracts'
import type { AlarmEvent } from '../../types'
import { authFetchJson } from './http'

export const realAlarmApi: AlarmApi = {
  listAlarms: () => authFetchJson<AlarmEvent[]>('/alarmes'),
}
