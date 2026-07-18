import type { SensorMeta, Threshold } from '../../types'

export const SENSOR: SensorMeta = {
  sensor_code: 'TEMP-EXP-01',
  name: 'Temperatura — Expurgo',
  unidade: 'C',
  protocolo_origem: 'rs485',
  measurement_type: { code: 'temperatura', name: 'Temperatura' },
  area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' },
}

export const THRESHOLD: Threshold = {
  sensor_id: 'TEMP-EXP-01',
  limite_min: 18,
  limite_max: 22,
  is_valor_padrao_regulatorio: true,
}
