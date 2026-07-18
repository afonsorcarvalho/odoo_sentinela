import type { SensorMeta, Threshold, HistoryResponse, LivePoint, Window } from '../types'

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
