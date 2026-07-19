import { describe, it, expect } from 'vitest'
import { mockConfigApi } from './configApi'
import type { DashboardLayout } from '../../layout/schema'

const layout: DashboardLayout = {
  version: 1, grid: { cols: 12, rowHeight: 40, margin: [8, 8] },
  widgets: [{ id: 'w1', type: 'kpi', layout: { x: 0, y: 0, w: 2, h: 2 }, binding: { sensorCode: 'S1' }, options: {} }],
}

describe('mockConfigApi', () => {
  it('getConfig traz carousel_interval_ms e layout', async () => {
    const cfg = await mockConfigApi.getConfig()
    expect(typeof cfg.carousel_interval_ms).toBe('number')
    expect('layout' in cfg).toBe(true)
  })
  it('saveLayout persiste em memória (round-trip via getConfig)', async () => {
    await mockConfigApi.saveLayout(layout)
    const cfg = await mockConfigApi.getConfig()
    expect(cfg.layout).toEqual(layout)
  })
})
