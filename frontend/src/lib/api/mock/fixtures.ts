import type { SensorMeta, Threshold } from '../../types'

// `area.category` e deliberadamente distinto de `area.name` nos fixtures
// abaixo. No modelo de dados real (odoo_modelo_dados_spec.md), `category`
// PODE ser igual a `name` — mas o AreaCard renderiza os dois como nos de
// texto separados, e strings identicas quebram buscas tipo `getByText`
// (e aparecem como texto duplicado na UI, ex.: "Expurgo / Expurgo").
export const SENSOR: SensorMeta = {
  sensor_code: 'TEMP-EXP-01',
  name: 'Temperatura — Expurgo',
  unidade: 'C',
  protocolo_origem: 'rs485',
  measurement_type: { code: 'temperatura', name: 'Temperatura' },
  area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Descontaminação' },
}

export const THRESHOLD: Threshold = {
  sensor_id: 'TEMP-EXP-01',
  limite_min: 18,
  limite_max: 22,
  is_valor_padrao_regulatorio: true,
}

const SENSOR_PREPARO: SensorMeta = {
  sensor_code: 'TEMP-PRE-01',
  name: 'Temperatura — Preparo/Esterilização',
  unidade: 'C',
  protocolo_origem: 'rs485',
  measurement_type: { code: 'temperatura', name: 'Temperatura' },
  area: { area_code: 'PREPARO_ESTER', name: 'Preparo/Esterilização', category: 'Esterilização' },
}

const THRESHOLD_PREPARO: Threshold = {
  sensor_id: 'TEMP-PRE-01',
  limite_min: 20,
  limite_max: 24,
  is_valor_padrao_regulatorio: true,
}

const SENSOR_ARSENAL: SensorMeta = {
  sensor_code: 'TEMP-ARS-01',
  name: 'Temperatura — Arsenal',
  unidade: 'C',
  protocolo_origem: 'rs485',
  measurement_type: { code: 'temperatura', name: 'Temperatura' },
  area: { area_code: 'ARSENAL', name: 'Arsenal', category: 'Armazenamento' },
}

// Pressao diferencial: valores reais de referencia RDC15 ja documentados em
// odoo_modelo_dados_spec.md §7 (Expurgo negativa min 2,5 Pa; Preparo positiva
// min 2,5 Pa). A regra real e unilateral ("mais negativa/positiva que X"),
// sem teto rigido documentado — o piso/teto extra abaixo (-15/15) e so um
// limite plausivel de mock p/ desenhar uma faixa, NAO e valor regulatorio.
const SENSOR_PRESSAO_EXP: SensorMeta = {
  sensor_code: 'PRESS-EXP-01',
  name: 'Pressão diferencial — Expurgo',
  unidade: 'Pa',
  protocolo_origem: 'rs485',
  measurement_type: { code: 'pressao_diferencial', name: 'Pressão diferencial' },
  area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Descontaminação' },
}

const THRESHOLD_PRESSAO_EXP: Threshold = {
  sensor_id: 'PRESS-EXP-01',
  limite_min: -15,
  limite_max: -2.5,
  is_valor_padrao_regulatorio: true,
}

const SENSOR_PRESSAO_PRE: SensorMeta = {
  sensor_code: 'PRESS-PRE-01',
  name: 'Pressão diferencial — Preparo/Esterilização',
  unidade: 'Pa',
  protocolo_origem: 'rs485',
  measurement_type: { code: 'pressao_diferencial', name: 'Pressão diferencial' },
  area: { area_code: 'PREPARO_ESTER', name: 'Preparo/Esterilização', category: 'Esterilização' },
}

const THRESHOLD_PRESSAO_PRE: Threshold = {
  sensor_id: 'PRESS-PRE-01',
  limite_min: 2.5,
  limite_max: 15,
  is_valor_padrao_regulatorio: true,
}

// Arsenal nao tem threshold regulatorio definido em odoo_modelo_dados_spec.md §7
// (so Expurgo e Preparo/Esterilizacao tem defaults RDC 15) — deliberadamente sem
// limite, exercita o estado "sem limite" do ThresholdBadge/computeStatus/AreaCard.
export const SENSORS: SensorMeta[] = [SENSOR, SENSOR_PREPARO, SENSOR_ARSENAL, SENSOR_PRESSAO_EXP, SENSOR_PRESSAO_PRE]

export const THRESHOLDS: Record<string, Threshold | null> = {
  [SENSOR.sensor_code]: THRESHOLD,
  [SENSOR_PREPARO.sensor_code]: THRESHOLD_PREPARO,
  [SENSOR_ARSENAL.sensor_code]: null,
  [SENSOR_PRESSAO_EXP.sensor_code]: THRESHOLD_PRESSAO_EXP,
  [SENSOR_PRESSAO_PRE.sensor_code]: THRESHOLD_PRESSAO_PRE,
}
