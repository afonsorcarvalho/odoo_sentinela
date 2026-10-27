import type { DashboardLayout } from './layout/schema'

export type Window = '1h' | '24h' | '7d' | '30d'

export type SensorMeta = {
  sensor_code: string
  name: string
  unidade: string
  protocolo_origem: '4-20ma' | 'rs485' | 'i2c'
  measurement_type: { code: string; name: string }
  area: { area_code: string; name: string; category: string }
}

export type Threshold = {
  sensor_id: string
  limite_min: number
  limite_max: number
  is_valor_padrao_regulatorio: boolean
}

export type DashboardConfig = {
  carousel_interval_ms: number
  carousel_transition_ms: number
  layout?: DashboardLayout | null
}

export type StatusLeitura = 'ok' | 'suspeito' | 'erro_leitura' | 'falha_sensor' | 'sensor_offline'

export type HistoryPoint =
  | { ts: number; value: number; status_leitura?: StatusLeitura }
  | { ts: number; min: number; max: number; avg: number }

export type HistoryResponse = {
  sensor_code: string
  window: Window
  resolution: 'raw' | 'agg'
  points: HistoryPoint[]
}

export type AlarmState = 'ok' | 'warn' | 'crit'

export type LivePoint = {
  sensor_code: string
  ts: number
  value: number
  alarm_state: AlarmState
  status_leitura?: StatusLeitura
}

// Estado da conexao de dados ao vivo (EventSource), derivado exclusivamente
// de onopen/onerror + readyState -- nunca de chegada/ausencia de dado (ver
// design doc A3, "Fora de escopo": silencio de dados e normal neste backend).
export type LiveConnectionState = 'live' | 'reconnecting' | 'offline'

export type AlarmEventStatus = 'aberto' | 'reconhecido' | 'resolvido'
export type AlarmTipoViolacao = 'acima_limite' | 'abaixo_limite' | 'sensor_offline' | 'erro_leitura'

// Evento de alarme empurrado ao vivo pelo mesmo SSE de /live (tipo:
// 'alarme_ao_vivo'), distinto de AlarmEvent (que vem do REST /alarmes com
// campos de ciclo de vida como status/usuario_responsavel).
export type LiveAlarme = {
  sensor_code: string
  area_code: string
  tipo_evento: 'entrada_alarme' | 'saida_alarme'
  tipo_violacao: string
  valor: number
  timestamp: string
}

export type AlarmEvent = {
  id: number
  sensor_code: string
  area_code: string
  timestamp_deteccao: number
  timestamp_resolucao_sensor: number | null
  valor_lido: number
  tipo_violacao: AlarmTipoViolacao
  limite_configurado_snapshot: number
  status: AlarmEventStatus
  usuario_responsavel: string | null
  data_resolucao: number | null
  observacoes: string | null
}
