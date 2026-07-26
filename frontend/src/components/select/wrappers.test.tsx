import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AreaSelect } from './AreaSelect'
import { SensorSelect } from './SensorSelect'

vi.mock('../../lib/queries', () => ({
  useSensors: () => ({ data: [
    { sensor_code: 'S1', name: 'Autoclave 1', unidade: '°C', protocolo_origem: '4-20ma',
      measurement_type: { code: 'temp', name: 'Temperatura' }, area: { area_code: 'A1', name: 'Expurgo', category: 'c' } },
    { sensor_code: 'S2', name: 'Camara Fria', unidade: '°C', protocolo_origem: '4-20ma',
      measurement_type: { code: 'temp', name: 'Temperatura' }, area: { area_code: 'A2', name: 'Arsenal', category: 'c' } },
  ] }),
}))

describe('wrappers', () => {
  it('SensorSelect resolve o label do sensor via useSensors', () => {
    render(<SensorSelect value="S2" onChange={vi.fn()} label="Sensor" />)
    expect(screen.getByDisplayValue('Camara Fria')).toBeInTheDocument()
  })
  it('AreaSelect deriva áreas dos sensores e mostra o label da área', () => {
    render(<AreaSelect value="A1" onChange={vi.fn()} label="Área" />)
    expect(screen.getByDisplayValue('Expurgo')).toBeInTheDocument()
  })
})
