import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

// ECharts mockado (sem canvas em jsdom) — SensorDetailPanel renderiza TimeSeriesChart.
vi.mock('echarts', () => ({ init: () => ({ setOption: vi.fn(), dispose: vi.fn(), resize: vi.fn() }) }))

import { SensorDetailPanel } from './SensorDetailPanel'
import type { AreaGroup } from '../lib/aggregateStatus'

const group: AreaGroup = {
  area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' },
  sensors: [
    { sensor_code: 'TEMP-EXP-01', name: 'Temp', unidade: '°C', protocolo_origem: '4-20ma', measurement_type: { code: 'temperatura', name: 'Temperatura' }, area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' } },
    { sensor_code: 'PRESS-EXP-01', name: 'Pressao', unidade: 'Pa', protocolo_origem: '4-20ma', measurement_type: { code: 'pressao_diferencial', name: 'Pressão' }, area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' } },
  ],
}

describe('SensorDetailPanel', () => {
  it('mostra titulo Area . Sensor, botoes de metrica para cada sensor da area, e a leitura', () => {
    render(
      <SensorDetailPanel
        group={group}
        selectedCode="TEMP-EXP-01"
        onSelectSensor={vi.fn()}
        threshold={{ sensor_id: 'TEMP-EXP-01', limite_min: 18, limite_max: 26, is_valor_padrao_regulatorio: false }}
        unidade="°C"
        value={21}
        state="ok"
        window="24h"
        onWindowChange={vi.fn()}
        history={undefined}
        tail={[]}
      />,
    )
    expect(screen.getByText('Detalhe do sensor')).toBeInTheDocument()
    expect(screen.getByText('Expurgo · Temperatura')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Temperatura' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pressão' })).toBeInTheDocument()
    expect(screen.getByText('21.0')).toBeInTheDocument()
  })

  it('clicar no botao de outra metrica chama onSelectSensor', () => {
    const onSelectSensor = vi.fn()
    render(
      <SensorDetailPanel
        group={group} selectedCode="TEMP-EXP-01" onSelectSensor={onSelectSensor}
        threshold={null} unidade="°C" value={21} state="ok"
        window="24h" onWindowChange={vi.fn()} history={undefined} tail={[]}
      />,
    )
    screen.getByRole('button', { name: 'Pressão' }).click()
    expect(onSelectSensor).toHaveBeenCalledWith('PRESS-EXP-01')
  })
})
