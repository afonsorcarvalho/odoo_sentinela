import { describe, it, expect } from 'vitest'
import { newWidget } from './newWidget'
import type { DashboardLayout } from '../layout/schema'

const base: DashboardLayout = { version: 1, grid: { cols: 12, rowHeight: 40, margin: [8, 8] }, widgets: [] }

describe('newWidget', () => {
  it('cria kpi com defaultSize e binding vazio', () => {
    const w = newWidget('kpi', base.widgets)
    expect(w.type).toBe('kpi')
    expect(w.layout.w).toBe(2)
    expect(w.binding).toEqual({})
  })
  it('gera ids únicos', () => {
    const w1 = newWidget('kpi', [])
    const w2 = newWidget('kpi', [w1])
    expect(w1.id).not.toBe(w2.id)
  })
})
