import { describe, it, expect, vi, afterEach } from 'vitest'
import { mockMetaApi } from './metaApi'
import { mockHistoryApi } from './historyApi'
import { mockLiveApi } from './liveApi'

afterEach(() => vi.useRealTimers())

describe('mockMetaApi', () => {
  it('devolve sensor e threshold da fixture', async () => {
    expect((await mockMetaApi.getSensor('x')).sensor_code).toBe('TEMP-EXP-01')
    expect((await mockMetaApi.getThreshold('x'))?.limite_max).toBe(22)
  })
})

describe('mockHistoryApi', () => {
  it('1h = raw, janela longa = agg', async () => {
    expect((await mockHistoryApi.getHistory('x', '1h')).resolution).toBe('raw')
    expect((await mockHistoryApi.getHistory('x', '30d')).resolution).toBe('agg')
  })
  it('nunca devolve mais de 1000 pontos', async () => {
    const r = await mockHistoryApi.getHistory('x', '30d')
    expect(r.points.length).toBeLessThanOrEqual(1000)
    expect(r.points.length).toBeGreaterThan(0)
  })
})

describe('mockLiveApi', () => {
  it('emite pontos incrementais e para no unsubscribe', () => {
    vi.useFakeTimers()
    const cb = vi.fn()
    const unsub = mockLiveApi.subscribe('x', cb)
    vi.advanceTimersByTime(3000)
    const afterThree = cb.mock.calls.length
    expect(afterThree).toBeGreaterThanOrEqual(2)
    unsub()
    vi.advanceTimersByTime(3000)
    expect(cb.mock.calls.length).toBe(afterThree) // parou
  })
  it('cada emissão é UM ponto com timestamp crescente', () => {
    vi.useFakeTimers()
    const pts: number[] = []
    const unsub = mockLiveApi.subscribe('x', (p) => pts.push(p.ts))
    vi.advanceTimersByTime(3000)
    unsub()
    for (let i = 1; i < pts.length; i++) expect(pts[i]).toBeGreaterThan(pts[i - 1])
  })
})
