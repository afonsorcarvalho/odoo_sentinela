import { describe, it, expect, vi, afterEach } from 'vitest'
import { realAlarmApi } from './alarmApi'

afterEach(() => vi.unstubAllGlobals())

describe('realAlarmApi', () => {
  it('listAlarms faz GET /alarmes', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [] })
    vi.stubGlobal('fetch', mockFetch)
    await realAlarmApi.listAlarms()
    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/alarmes'), expect.anything())
  })
})
