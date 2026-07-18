import { describe, it, expect, vi, afterEach } from 'vitest'
import { realHistoryApi } from './historyApi'

afterEach(() => vi.unstubAllGlobals())

describe('realHistoryApi', () => {
  it('getHistory chama GET /sensores/{code}/historico?window={window} e devolve o JSON', async () => {
    const body = {
      sensor_code: 'SNR-1',
      window: '1h',
      resolution: 'raw',
      points: [{ ts: 1700000000000, value: 20.1 }],
    }
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => body })
    vi.stubGlobal('fetch', mockFetch)

    const result = await realHistoryApi.getHistory('SNR-1', '1h')

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/sensores/SNR-1/historico?window=1h'),
      expect.anything(),
    )
    expect(result).toEqual(body)
  })
})
