import { describe, it, expect } from 'vitest'
import { sensorDisplayState, worstAlarmState, groupSensorsByArea } from './aggregateStatus'
import type { LivePoint, SensorMeta, Threshold } from './types'

const t: Threshold = { sensor_id: 'S', limite_min: 18, limite_max: 22, is_valor_padrao_regulatorio: true }
const okPoint: LivePoint = { sensor_code: 'S', ts: 1, value: 20, alarm_state: 'ok' }
const critPoint: LivePoint = { sensor_code: 'S', ts: 1, value: 30, alarm_state: 'crit' }

describe('sensorDisplayState', () => {
  it('sem threshold e sempre unknown, mesmo com feed reportando ok', () => {
    expect(sensorDisplayState(null, okPoint)).toBe('unknown')
  })
  it('sem dado ao vivo ainda e unknown', () => {
    expect(sensorDisplayState(t, undefined)).toBe('unknown')
  })
  it('com threshold e dado, usa o alarm_state do feed', () => {
    expect(sensorDisplayState(t, okPoint)).toBe('ok')
    expect(sensorDisplayState(t, critPoint)).toBe('crit')
  })
})

describe('worstAlarmState', () => {
  it('vazio e unknown', () => {
    expect(worstAlarmState([])).toBe('unknown')
  })
  it('todos ok e ok', () => {
    expect(worstAlarmState(['ok', 'ok'])).toBe('ok')
  })
  it('um crit entre varios ok e crit', () => {
    expect(worstAlarmState(['ok', 'crit', 'ok'])).toBe('crit')
  })
  it('um warn entre ok (sem crit) e warn', () => {
    expect(worstAlarmState(['ok', 'warn'])).toBe('warn')
  })
  it('crit tem prioridade sobre warn', () => {
    expect(worstAlarmState(['warn', 'crit'])).toBe('crit')
  })
  it('todos unknown e unknown', () => {
    expect(worstAlarmState(['unknown', 'unknown'])).toBe('unknown')
  })
})

describe('groupSensorsByArea', () => {
  const sExp: SensorMeta = {
    sensor_code: 'A', name: 'a', unidade: 'C', protocolo_origem: 'rs485',
    measurement_type: { code: 'temperatura', name: 'Temperatura' },
    area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' },
  }
  const sPre: SensorMeta = {
    ...sExp, sensor_code: 'B',
    area: { area_code: 'PREPARO_ESTER', name: 'Preparo/Esterilização', category: 'Preparo/Esterilização' },
  }
  const sExp2: SensorMeta = { ...sExp, sensor_code: 'C' }

  it('agrupa sensores pela area_code, preservando ordem de primeira ocorrencia', () => {
    const groups = groupSensorsByArea([sExp, sPre, sExp2])
    expect(groups).toHaveLength(2)
    expect(groups[0].area.area_code).toBe('EXPURGO')
    expect(groups[0].sensors.map((s) => s.sensor_code)).toEqual(['A', 'C'])
    expect(groups[1].area.area_code).toBe('PREPARO_ESTER')
    expect(groups[1].sensors.map((s) => s.sensor_code)).toEqual(['B'])
  })
  it('lista vazia devolve grupos vazios', () => {
    expect(groupSensorsByArea([])).toEqual([])
  })
})
