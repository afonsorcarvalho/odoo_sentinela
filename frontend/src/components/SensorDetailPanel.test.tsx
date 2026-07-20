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

  // DT/M2 (docs/superpowers/specs/2026-07-19-widget-drilldown-sensor-detail-design.md):
  // o teste NAO consegue medir a altura renderizada real (echarts mockado,
  // sem canvas em jsdom -- ver comentario no topo deste arquivo). Isso e
  // validado no browser (Playwright), fora do escopo de T1. O que da para
  // provar aqui, honestamente, e a ESTRUTURA que faz o preenchimento de
  // altura funcionar quando um ancestral (o drawer, em T2/T3) tiver altura
  // definida: painel = coluna flex full-height, chart embrulhado num
  // wrapper min-h-0 flex-1 -- mesmo padrao ja provado em TimeseriesWidget.tsx.
  it('e uma coluna flex full-height (h-full flex-col) com o TimeSeriesChart num wrapper min-h-0 flex-1 (DT/M2)', () => {
    const { container } = render(
      <SensorDetailPanel
        group={group} selectedCode="TEMP-EXP-01" onSelectSensor={vi.fn()}
        threshold={null} unidade="°C" value={21} state="ok"
        window="24h" onWindowChange={vi.fn()} history={undefined} tail={[]}
      />,
    )

    const root = container.firstElementChild as HTMLElement
    expect(root.classList.contains('flex')).toBe(true)
    expect(root.classList.contains('h-full')).toBe(true)
    expect(root.classList.contains('flex-col')).toBe(true)

    const chartWrapper = screen.getByTestId('sensor-detail-chart-wrapper')
    expect(chartWrapper.classList.contains('min-h-0')).toBe(true)
    expect(chartWrapper.classList.contains('flex-1')).toBe(true)
    // TimeSeriesChart deve estar DENTRO do wrapper, nao como filho nu do painel.
    expect(chartWrapper.querySelector('div')).not.toBeNull()
  })
})
