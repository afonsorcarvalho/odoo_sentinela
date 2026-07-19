import type { SensorMeta, Threshold, HistoryResponse, LivePoint, Window, AlarmEvent, DashboardConfig } from '../types'

export type MetaApi = {
  getSensor(code: string): Promise<SensorMeta>
  getThreshold(code: string): Promise<Threshold | null>
  listSensors(): Promise<SensorMeta[]>
}
export type HistoryApi = {
  getHistory(code: string, window: Window): Promise<HistoryResponse>
}
export type LiveApi = {
  subscribe(code: string, cb: (p: LivePoint) => void): () => void
}

export type AuthApi = {
  login(usuario: string, senha: string): Promise<{ access_token: string; token_type: string }>
}
export type AlarmApi = {
  listAlarms(): Promise<AlarmEvent[]>
}
export type ConfigApi = {
  getConfig(): Promise<DashboardConfig>
}
