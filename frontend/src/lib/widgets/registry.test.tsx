import { describe, it, expect } from 'vitest'
import { WIDGET_REGISTRY } from './registry'
import { WIDGET_TYPES } from '../layout/schema'

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
})
