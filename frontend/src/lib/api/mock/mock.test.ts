import { describe, it, expect, vi, afterEach } from 'vitest'
import { mockMetaApi } from './metaApi'
import { mockHistoryApi } from './historyApi'
import { mockLiveApi } from './liveApi'

afterEach(() => vi.useRealTimers())

describe('mockMetaApi', () => {
  it('getSensor/getThreshold buscam pelo codigo real (TEMP-EXP-01, ja existente)', async () => {
    expect((await mockMetaApi.getSensor('TEMP-EXP-01')).sensor_code).toBe('TEMP-EXP-01')
    expect((await mockMetaApi.getThreshold('TEMP-EXP-01'))?.limite_max).toBe(22)
  })
  it('listSensors devolve os 3 sensores (Expurgo, Preparo/Esterilizacao, Arsenal)', async () => {
    const sensors = await mockMetaApi.listSensors()
    const codes = sensors.map((s) => s.sensor_code).sort()
    expect(codes).toEqual(['TEMP-ARS-01', 'TEMP-EXP-01', 'TEMP-PRE-01'])
  })
  it('Preparo/Esterilizacao tem threshold 20-24', async () => {
    const t = await mockMetaApi.getThreshold('TEMP-PRE-01')
    expect(t).toEqual({ sensor_id: 'TEMP-PRE-01', limite_min: 20, limite_max: 24, is_valor_padrao_regulatorio: true })
  })
  it('Arsenal nao tem threshold (null, sem lancar erro)', async () => {
    const sensor = await mockMetaApi.getSensor('TEMP-ARS-01')
    expect(sensor.area.name).toBe('Arsenal')
    expect(await mockMetaApi.getThreshold('TEMP-ARS-01')).toBeNull()
  })
  it('codigo desconhecido lanca erro em getSensor e getThreshold', async () => {
    await expect(mockMetaApi.getSensor('NAO-EXISTE')).rejects.toThrow()
    await expect(mockMetaApi.getThreshold('NAO-EXISTE')).rejects.toThrow()
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

  it('TEMP-EXP-01 mantem comportamento existente: nunca cruza a faixa (sempre ok/warn)', () => {
    vi.useFakeTimers()
    const states = new Set<string>()
    const unsub = mockLiveApi.subscribe('TEMP-EXP-01', (p) => states.add(p.alarm_state))
    vi.advanceTimersByTime(20000)
    unsub()
    expect(states.has('crit')).toBe(false)
  })

  it('TEMP-PRE-01 (Preparo) cruza a faixa periodicamente: produz crit', () => {
    vi.useFakeTimers()
    const states = new Set<string>()
    const unsub = mockLiveApi.subscribe('TEMP-PRE-01', (p) => states.add(p.alarm_state))
    vi.advanceTimersByTime(20000)
    unsub()
    expect(states.has('crit')).toBe(true)
  })

  it('TEMP-ARS-01 (sem threshold) sempre reporta ok, independente do valor', () => {
    vi.useFakeTimers()
    const states = new Set<string>()
    const unsub = mockLiveApi.subscribe('TEMP-ARS-01', (p) => states.add(p.alarm_state))
    vi.advanceTimersByTime(20000)
    unsub()
    expect([...states]).toEqual(['ok'])
  })
})
