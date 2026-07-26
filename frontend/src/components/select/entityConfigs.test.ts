import { describe, it, expect } from 'vitest'
import { deriveAreas, areaConfig, sensorConfig } from './entityConfigs'
import type { SensorMeta } from '../../lib/types'

const s = (over: Partial<SensorMeta> = {}): SensorMeta => ({
  sensor_code: 'S1', name: 'Sensor Um', unidade: '°C',
  protocolo_origem: '4-20ma', measurement_type: { code: 'temp', name: 'Temperatura' },
  area: { area_code: 'A1', name: 'Expurgo', category: 'critica' },
  ...over,
})

describe('deriveAreas', () => {
  it('dedup por area_code e ordena por name', () => {
    const areas = deriveAreas([
      s({ sensor_code: 'S1', area: { area_code: 'A2', name: 'Preparo', category: 'c' } }),
      s({ sensor_code: 'S2', area: { area_code: 'A1', name: 'Arsenal', category: 'c' } }),
      s({ sensor_code: 'S3', area: { area_code: 'A2', name: 'Preparo', category: 'c' } }),
    ])
    expect(areas.map((a) => a.area_code)).toEqual(['A1', 'A2']) // Arsenal < Preparo
  })
})

describe('sensorConfig', () => {
  it('searchText casa em nome, código, área e tipo (multi-campo)', () => {
    const t = sensorConfig.searchText(s()).toLowerCase()
    expect(t).toContain('sensor um')
    expect(t).toContain('s1')
    expect(t).toContain('expurgo')
    expect(t).toContain('temperatura')
  })
  it('colunas incluem Nome, Código, Área, Tipo, Unidade', () => {
    expect(sensorConfig.columns.map((c) => c.header)).toEqual(['Nome', 'Código', 'Área', 'Tipo', 'Unidade'])
  })
  it('getId/getLabel usam sensor_code/name', () => {
    expect(sensorConfig.getId(s())).toBe('S1')
    expect(sensorConfig.getLabel(s())).toBe('Sensor Um')
  })
})

describe('areaConfig', () => {
  it('searchText casa em nome, código e categoria', () => {
    const a = { area_code: 'A1', name: 'Expurgo', category: 'critica' }
    const t = areaConfig.searchText(a).toLowerCase()
    expect(t).toContain('expurgo')
    expect(t).toContain('a1')
    expect(t).toContain('critica')
  })
  it('colunas incluem Nome, Código, Categoria', () => {
    expect(areaConfig.columns.map((c) => c.header)).toEqual(['Nome', 'Código', 'Categoria'])
  })
})
