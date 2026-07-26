import type { SensorMeta, Threshold, HistoryResponse, LivePoint, Window, AlarmEvent, DashboardConfig, LiveConnectionState, LiveAlarme } from '../types'
import type { DashboardLayout } from '../layout/schema'

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
  // Estado da conexao (transporte), agnostico de sensor. Emite o estado atual
  // na inscricao e a cada transicao subsequente; mock reporta 'live' sempre
  // (nao ha rede a monitorar) -- ver design doc A3.
  subscribeConnection(cb: (s: LiveConnectionState) => void): () => void
  // Alarmes empurrados ao vivo pelo mesmo SSE de /live (tipo: 'alarme_ao_vivo'),
  // demuxados do fluxo de leituras -- ver real/liveApi.ts onmessage.
  subscribeAlarme(cb: (a: LiveAlarme) => void): () => void
}

export type AuthApi = {
  login(usuario: string, senha: string): Promise<{ access_token: string; token_type: string }>
}
export type AlarmApi = {
  listAlarms(): Promise<AlarmEvent[]>
}
export type ConfigApi = {
  getConfig(): Promise<DashboardConfig>
  saveLayout(layout: DashboardLayout): Promise<{ layout: DashboardLayout }>
}
