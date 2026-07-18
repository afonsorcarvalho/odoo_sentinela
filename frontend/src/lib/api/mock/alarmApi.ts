import type { AlarmApi } from '../contracts'
import type { AlarmEvent } from '../../types'

const NOW = 1_700_000_000_000

const FIXTURE: AlarmEvent[] = [
  {
    id: 2, sensor_code: 'PRESS-EXP-01', area: { area_code: 'EXPURGO', name: 'Expurgo' },
    tipo_violacao: 'abaixo_limite', status: 'aberto',
    timestamp_deteccao: new Date(NOW).toISOString(),
    valor_lido: -1.7, limite_configurado_snapshot: -2.5, data_resolucao: null,
  },
  {
    id: 1, sensor_code: 'TEMP-PRE-01', area: { area_code: 'PREPARO', name: 'Preparo' },
    tipo_violacao: 'acima_limite', status: 'resolvido',
    timestamp_deteccao: new Date(NOW - 600_000).toISOString(),
    valor_lido: 24.1, limite_configurado_snapshot: 23.0, data_resolucao: new Date(NOW - 300_000).toISOString(),
  },
]

export const mockAlarmApi: AlarmApi = {
  async listAlarms() {
    return FIXTURE
  },
}
