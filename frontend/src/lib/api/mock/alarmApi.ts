import type { AlarmApi } from '../contracts'
import type { AlarmEvent } from '../../types'

const NOW = 1_700_000_000_000

const FIXTURE: AlarmEvent[] = [
  {
    id: 2, sensor_code: 'PRESS-EXP-01', area_code: 'EXPURGO',
    tipo_violacao: 'abaixo_limite', status: 'aberto',
    timestamp_deteccao: NOW, timestamp_resolucao_sensor: null,
    valor_lido: -1.7, limite_configurado_snapshot: -2.5,
    usuario_responsavel: null, data_resolucao: null, observacoes: null,
  },
  {
    id: 1, sensor_code: 'TEMP-PRE-01', area_code: 'PREPARO',
    tipo_violacao: 'acima_limite', status: 'resolvido',
    timestamp_deteccao: NOW - 600_000, timestamp_resolucao_sensor: NOW - 500_000,
    valor_lido: 24.1, limite_configurado_snapshot: 23.0,
    usuario_responsavel: 'Ana Enfermeira', data_resolucao: NOW - 300_000,
    observacoes: 'Janela aberta por engano, sensor normalizou apos fechamento.',
  },
]

export const mockAlarmApi: AlarmApi = {
  async listAlarms() {
    return FIXTURE
  },
}
