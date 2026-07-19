import { describe, it, expect, vi, afterEach } from 'vitest'
import { realConfigApi } from './configApi'

afterEach(() => vi.unstubAllGlobals())

describe('realConfigApi', () => {
  it('getConfig chama GET /config e devolve o JSON', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ carousel_interval_ms: 7000 }) })
    vi.stubGlobal('fetch', mockFetch)

    const result = await realConfigApi.getConfig()

    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/config'), expect.anything())
    expect(result).toEqual({ carousel_interval_ms: 7000 })
  })
})
