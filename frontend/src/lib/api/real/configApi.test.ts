import { describe, it, expect, vi, afterEach } from 'vitest'
import { realConfigApi } from './configApi'
import type { DashboardLayout } from '../../layout/schema'

afterEach(() => vi.unstubAllGlobals())

describe('realConfigApi', () => {
  it('getConfig chama GET /config e devolve o JSON', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ carousel_interval_ms: 7000, layout: null }) })
    vi.stubGlobal('fetch', mockFetch)
    const result = await realConfigApi.getConfig()
    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/config'), expect.anything())
    expect(result).toEqual({ carousel_interval_ms: 7000, layout: null })
  })

  it('saveLayout faz PUT /config/layout com body { layout }', async () => {
    const layout: DashboardLayout = {
      version: 1, grid: { cols: 12, rowHeight: 40, margin: [8, 8] }, widgets: [],
    }
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ layout }) })
    vi.stubGlobal('fetch', mockFetch)
    const result = await realConfigApi.saveLayout(layout)
    const [url, init] = mockFetch.mock.calls[0]
    expect(url).toContain('/config/layout')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body)).toEqual({ layout })
    expect(result).toEqual({ layout })
  })
})
