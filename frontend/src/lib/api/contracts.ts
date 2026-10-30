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

export type Granularidade = 'hora' | 'dia' | 'mes'
export type ReportBucketEstado = 'ok' | 'falha_instrumento' | 'sem_dados'
export type ReportBucket = {
  bucket: string // ISO com offset local (America/Sao_Paulo)
  avg: number | null
  min: number | null
  max: number | null
  n_ok: number
  n_falha: number
  estado: ReportBucketEstado
  fora_limite: boolean
}
export type ReportLimiteAlteracao = {
  quando: string // ISO UTC
  campo: string // 'limite_min' | 'limite_max'
  de: number | null
  para: number | null
}
export type ReportSensor = {
  sensor_code: string
  nome: string
  unidade: string
  site: string | null
  area: string | null
  endereco: string | null
  localizacao: string | null
  limites: { limite_min: number | null; limite_max: number | null } | null
  alteracoes_limite: ReportLimiteAlteracao[]
  buckets: ReportBucket[]
  alarmes: AlarmEvent[]
}
export type Report = {
  inicio: string // AAAA-MM-DD
  fim: string
  granularidade: Granularidade
  fuso: string
  emitido_em: string
  emissor: string
  sensores: ReportSensor[]
}
export type ReportParams = { sensores: string[]; inicio: string; fim: string }
export type ReportApi = {
  getReport(p: ReportParams): Promise<Report>
  getReportPdf(p: ReportParams): Promise<Blob>
}
