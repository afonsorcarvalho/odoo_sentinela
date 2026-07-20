import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { WIDGET_REGISTRY } from './registry'
import { WIDGET_TYPES } from '../layout/schema'
import type { WidgetInstance } from '../layout/schema'

vi.mock('../../components/widgets/KpiWidget', () => ({
  KpiWidget: (props: { limiteMin?: number; limiteMax?: number }) => (
    <div data-testid="kpi" data-limite-min={props.limiteMin} data-limite-max={props.limiteMax} />
  ),
}))

vi.mock('../../components/widgets/AlarmsWidget', () => ({
  AlarmsWidget: (props: { scope: 'site' | 'area'; areaCodes: string[] }) => (
    <div data-testid="alarms" data-scope={props.scope} data-area-codes={JSON.stringify(props.areaCodes)} />
  ),
}))

function widget(overrides: Partial<WidgetInstance>): WidgetInstance {
  return {
    id: 'w1',
    type: 'kpi',
    layout: { x: 0, y: 0, w: 2, h: 2 },
    binding: {},
    options: {},
    ...overrides,
  } as WidgetInstance
}

describe('WIDGET_REGISTRY', () => {
  it('tem descriptor para cada WidgetType', () => {
    for (const t of WIDGET_TYPES) {
      expect(WIDGET_REGISTRY[t]).toBeDefined()
      expect(WIDGET_REGISTRY[t].label).toBeTruthy()
      expect(WIDGET_REGISTRY[t].defaultSize.w).toBeGreaterThan(0)
      expect(['area', 'sensor', 'none']).toContain(WIDGET_REGISTRY[t].needs)
    }
  })
  it('area precisa de area, timeseries/kpi de sensor, alarms de none', () => {
    expect(WIDGET_REGISTRY.area.needs).toBe('area')
    expect(WIDGET_REGISTRY.timeseries.needs).toBe('sensor')
    expect(WIDGET_REGISTRY.kpi.needs).toBe('sensor')
    expect(WIDGET_REGISTRY.alarms.needs).toBe('none')
  })

  it('kpi.render passa limiteMin/limiteMax de options para o KpiWidget', () => {
    const w = widget({ binding: { sensorCode: 'S1' }, options: { limiteMin: 10, limiteMax: 50 } })
    render(<>{WIDGET_REGISTRY.kpi.render(w)}</>)
    const el = screen.getByTestId('kpi')
    expect(el.dataset.limiteMin).toBe('10')
    expect(el.dataset.limiteMax).toBe('50')
  })

  it('kpi.render sem options -> limiteMin/limiteMax undefined (sem override)', () => {
    const w = widget({ binding: { sensorCode: 'S1' }, options: {} })
    render(<>{WIDGET_REGISTRY.kpi.render(w)}</>)
    const el = screen.getByTestId('kpi')
    expect(el.dataset.limiteMin).toBeUndefined()
    expect(el.dataset.limiteMax).toBeUndefined()
  })

  it('alarms.render com binding.areaCodes -> passa areaCodes tal qual', () => {
    const w = widget({ type: 'alarms', binding: { areaCodes: ['a', 'b'] }, options: { scope: 'area' } })
    render(<>{WIDGET_REGISTRY.alarms.render(w)}</>)
    const el = screen.getByTestId('alarms')
    expect(el.dataset.scope).toBe('area')
    expect(JSON.parse(el.dataset.areaCodes ?? '[]')).toEqual(['a', 'b'])
  })

  it('alarms.render legado (só binding.areaCode) -> resolve para [areaCode]', () => {
    const w = widget({ type: 'alarms', binding: { areaCode: 'a' }, options: { scope: 'area' } })
    render(<>{WIDGET_REGISTRY.alarms.render(w)}</>)
    const el = screen.getByTestId('alarms')
    expect(JSON.parse(el.dataset.areaCodes ?? '[]')).toEqual(['a'])
  })

  it('alarms.render sem área -> passa areaCodes vazio', () => {
    const w = widget({ type: 'alarms', binding: {}, options: { scope: 'site' } })
    render(<>{WIDGET_REGISTRY.alarms.render(w)}</>)
    const el = screen.getByTestId('alarms')
    expect(JSON.parse(el.dataset.areaCodes ?? '[]')).toEqual([])
  })
})
