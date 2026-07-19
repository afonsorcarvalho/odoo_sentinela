import { describe, it, expect } from 'vitest'
import { parseLayout, migrate } from './schema'

const validLayout = {
  version: 1,
  grid: { cols: 12, rowHeight: 40, margin: [8, 8] },
  widgets: [
    { id: 'w1', type: 'kpi', layout: { x: 0, y: 0, w: 2, h: 2 }, binding: { sensorCode: 'S1' }, options: {} },
  ],
}

describe('parseLayout', () => {
  it('aceita layout válido', () => {
    expect(parseLayout(validLayout)).toEqual(validLayout)
  })
  it('devolve null para não-objeto', () => {
    expect(parseLayout('nope')).toBeNull()
    expect(parseLayout(null)).toBeNull()
  })
  it('devolve null quando widget tem type desconhecido', () => {
    const bad = { ...validLayout, widgets: [{ ...validLayout.widgets[0], type: 'foo' }] }
    expect(parseLayout(bad)).toBeNull()
  })
  it('devolve null quando falta layout.x', () => {
    const bad = { ...validLayout, widgets: [{ ...validLayout.widgets[0], layout: { y: 0, w: 2, h: 2 } }] }
    expect(parseLayout(bad)).toBeNull()
  })
})

describe('migrate', () => {
  it('é no-op para version 1', () => {
    expect(migrate(validLayout)).toEqual(validLayout)
  })
})
