import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { realLiveApi } from './liveApi'
import { TOKEN_STORAGE_KEY } from '../../useAuth'
import * as metaApiModule from './metaApi'

class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  onmessage: ((ev: { data: string }) => void) | null = null
  closed = false
  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }
  close() {
    this.closed = true
  }
}

const THRESHOLD = { sensor_id: 'SNR-1', limite_min: 10, limite_max: 20, is_valor_padrao_regulatorio: false }

beforeEach(() => {
  MockEventSource.instances = []
  vi.stubGlobal('EventSource', MockEventSource)
})

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('realLiveApi', () => {
  it('subscribe abre EventSource com sensor_code e token na URL', () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'abc.def.ghi')
    vi.spyOn(metaApiModule.realMetaApi, 'getThreshold').mockResolvedValue(THRESHOLD)

    realLiveApi.subscribe('SNR-1', () => {})

    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0].url).toContain('/sensores/SNR-1/live')
    expect(MockEventSource.instances[0].url).toContain('token=abc.def.ghi')
  })

  it('onmessage computa alarm_state a partir do threshold cacheado e chama cb com LivePoint', async () => {
    vi.spyOn(metaApiModule.realMetaApi, 'getThreshold').mockResolvedValue(THRESHOLD)
    const cb = vi.fn()

    realLiveApi.subscribe('SNR-1', cb)
    await Promise.resolve()

    const es = MockEventSource.instances[0]
    es.onmessage?.({ data: JSON.stringify({ sensor_id: 'SNR-1', time: 1700000000000, valor: 15 }) })

    expect(cb).toHaveBeenCalledWith({
      sensor_code: 'SNR-1', ts: 1700000000000, value: 15, alarm_state: 'ok',
    })
  })

  it('valor fora da faixa do threshold gera alarm_state crit', async () => {
    vi.spyOn(metaApiModule.realMetaApi, 'getThreshold').mockResolvedValue(THRESHOLD)
    const cb = vi.fn()

    realLiveApi.subscribe('SNR-1', cb)
    await Promise.resolve()

    const es = MockEventSource.instances[0]
    es.onmessage?.({ data: JSON.stringify({ sensor_id: 'SNR-1', time: 1700000000000, valor: 99 }) })

    expect(cb).toHaveBeenCalledWith(expect.objectContaining({ alarm_state: 'crit' }))
  })

  it('threshold ainda nao chegou (mensagem antes do fetch resolver) cai em alarm_state ok', () => {
    // não mocka getThreshold — simula que a promise ainda não resolveu
    const cb = vi.fn()

    realLiveApi.subscribe('SNR-1', cb)
    // sem await — dispara a mensagem antes da promise de threshold resolver

    const es = MockEventSource.instances[0]
    es.onmessage?.({ data: JSON.stringify({ sensor_id: 'SNR-1', time: 1700000000000, valor: 999 }) })

    expect(cb).toHaveBeenCalledWith(expect.objectContaining({ alarm_state: 'ok' }))
  })

  it('unsubscribe fecha o EventSource', () => {
    vi.spyOn(metaApiModule.realMetaApi, 'getThreshold').mockResolvedValue(THRESHOLD)

    const unsubscribe = realLiveApi.subscribe('SNR-1', () => {})
    unsubscribe()

    expect(MockEventSource.instances[0].closed).toBe(true)
  })
})
