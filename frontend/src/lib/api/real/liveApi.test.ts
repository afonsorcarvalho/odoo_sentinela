import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { realLiveApi } from './liveApi'
import { realMetaApi } from './metaApi'
import { realHistoryApi } from './historyApi'

vi.mock('./metaApi', () => ({ realMetaApi: { getThreshold: vi.fn() } }))
vi.mock('./historyApi', () => ({ realHistoryApi: { getHistory: vi.fn() } }))

beforeEach(() => {
  vi.useFakeTimers()
  vi.mocked(realMetaApi.getThreshold).mockResolvedValue({
    sensor_id: 'A', limite_min: 10, limite_max: 20, is_valor_padrao_regulatorio: false,
  })
  vi.mocked(realHistoryApi.getHistory).mockResolvedValue({
    sensor_code: 'A', window: '1h', resolution: 'raw', points: [{ ts: 1000, value: 25 }],
  })
})
afterEach(() => vi.useRealTimers())

describe('realLiveApi', () => {
  it('subscribe busca o historico e emite o ultimo ponto com alarm_state derivado do threshold', async () => {
    const cb = vi.fn()
    realLiveApi.subscribe('A', cb)
    await vi.runOnlyPendingTimersAsync()

    expect(cb).toHaveBeenCalledWith({ sensor_code: 'A', ts: 1000, value: 25, alarm_state: 'crit' })
  })

  it('unsubscribe para o polling', async () => {
    const cb = vi.fn()
    const unsub = realLiveApi.subscribe('A', cb)
    await vi.runOnlyPendingTimersAsync()
    cb.mockClear()
    unsub()

    await vi.advanceTimersByTimeAsync(10_000)
    expect(cb).not.toHaveBeenCalled()
  })
})
