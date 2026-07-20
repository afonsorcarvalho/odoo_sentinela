import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { realLiveApi } from './liveApi'
import { TOKEN_STORAGE_KEY } from '../../useAuth'
import * as metaApiModule from './metaApi'
import type { LivePoint } from '../../types'

class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  onmessage: ((ev: { data: string }) => void) | null = null
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  // 1 = OPEN por padrao: os testes de demux/subscribe existentes nao exercitam
  // onopen e tratam a conexao como ja estabelecida.
  readyState = 1
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

// Helper de teste: rastreia toda unsubscribe function criada em qualquer `it()`
// pra garantir que nenhum teste termine com inscricao pendurada no singleton de
// modulo de liveApi.ts (sharedSource/subscribers) -- sem isso, o estado vaza pro
// proximo teste do mesmo arquivo (Vitest isola modulos por arquivo, nao por `it`).
// Idempotente: chamar a mesma unsub 2x (uma explicita no meio do teste, outra no
// afterEach) e seguro, pois closeSharedSourceIfIdle()/callbacks.delete() em
// liveApi.ts ja sao seguros de chamar mais de uma vez.
let unsubs: Array<() => void> = []
function subscribe(code: string, cb: (p: LivePoint) => void) {
  const unsub = realLiveApi.subscribe(code, cb)
  unsubs.push(unsub)
  return unsub
}

// Mesma logica do array `unsubs` acima, para a subscription paralela de
// estado de conexao -- sem isto, listeners de um `it()' vazam pro proximo
// (Vitest isola modulo por arquivo, nao por teste) e recebem transicoes de
// testes que nao os criaram.
let connectionUnsubs: Array<() => void> = []
function subscribeConnection(cb: (s: string) => void) {
  const unsub = realLiveApi.subscribeConnection(cb)
  connectionUnsubs.push(unsub)
  return unsub
}

beforeEach(() => {
  MockEventSource.instances = []
  vi.stubGlobal('EventSource', MockEventSource)
  vi.spyOn(metaApiModule.realMetaApi, 'getThreshold').mockResolvedValue(THRESHOLD)
})

afterEach(() => {
  unsubs.forEach((fn) => fn())
  unsubs = []
  connectionUnsubs.forEach((fn) => fn())
  connectionUnsubs = []
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  vi.useRealTimers()
  localStorage.clear()
})

describe('realLiveApi', () => {
  it('subscribe abre 1 unico EventSource pra /live (sem sensor_code na URL), reusado por chamadas seguintes', () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'abc.def.ghi')

    subscribe('SNR-1', () => {})
    subscribe('SNR-2', () => {})
    subscribe('SNR-3', () => {})

    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0].url).toContain('/live?token=abc.def.ghi')
    expect(MockEventSource.instances[0].url).not.toContain('/sensores/')
  })

  it('demuxa mensagens por sensor_id: cada callback so recebe evento do seu proprio sensor', async () => {
    const cbA = vi.fn()
    const cbB = vi.fn()
    subscribe('SNR-1', cbA)
    subscribe('SNR-2', cbB)
    await Promise.resolve()

    const es = MockEventSource.instances[0]
    es.onmessage?.({ data: JSON.stringify({ sensor_id: 'SNR-1', time: 1700000000000, valor: 15 }) })

    expect(cbA).toHaveBeenCalledTimes(1)
    expect(cbB).not.toHaveBeenCalled()
  })

  it('onmessage computa alarm_state a partir do threshold cacheado do proprio sensor', async () => {
    const cb = vi.fn()
    subscribe('SNR-1', cb)
    await Promise.resolve()

    const es = MockEventSource.instances[0]
    es.onmessage?.({ data: JSON.stringify({ sensor_id: 'SNR-1', time: 1700000000000, valor: 15 }) })

    expect(cb).toHaveBeenCalledWith({ sensor_code: 'SNR-1', ts: 1700000000000, value: 15, alarm_state: 'ok' })
  })

  it('valor fora da faixa do threshold gera alarm_state crit', async () => {
    const cb = vi.fn()
    subscribe('SNR-1', cb)
    await Promise.resolve()

    const es = MockEventSource.instances[0]
    es.onmessage?.({ data: JSON.stringify({ sensor_id: 'SNR-1', time: 1700000000000, valor: 99 }) })

    expect(cb).toHaveBeenCalledWith(expect.objectContaining({ alarm_state: 'crit' }))
  })

  it('unsubscribe de 1 sensor nao fecha o EventSource compartilhado enquanto outros seguem inscritos', async () => {
    const unsubA = subscribe('SNR-1', () => {})
    subscribe('SNR-2', () => {})

    unsubA()

    expect(MockEventSource.instances[0].closed).toBe(false)
  })

  it('unsubscribe do ultimo inscrito fecha o EventSource compartilhado', () => {
    const unsubA = subscribe('SNR-1', () => {})
    unsubA()

    expect(MockEventSource.instances[0].closed).toBe(true)
  })

  it('reabre um novo EventSource se subscribe for chamado de novo apos todo mundo sair', () => {
    const unsubA = subscribe('SNR-1', () => {})
    unsubA()
    subscribe('SNR-2', () => {})

    expect(MockEventSource.instances).toHaveLength(2)
    expect(MockEventSource.instances[1].closed).toBe(false)
  })

  it('unsubscribe stale (chamado 2x com resubscribe no meio) nao apaga o inscrito novo', async () => {
    const cbOld = vi.fn()
    const cbNew = vi.fn()

    const unsubOld = subscribe('SNR-1', cbOld)
    unsubOld()

    subscribe('SNR-1', cbNew)
    unsubOld()
    await Promise.resolve()

    const es = MockEventSource.instances[MockEventSource.instances.length - 1]
    es.onmessage?.({ data: JSON.stringify({ sensor_id: 'SNR-1', time: 1700000000000, valor: 15 }) })

    expect(cbNew).toHaveBeenCalledTimes(1)
    expect(cbOld).not.toHaveBeenCalled()
  })

  it('sensor_code vazio: nao registra callback, nao quebra o demux dos outros', () => {
    const cb = vi.fn()
    const unsubscribe = subscribe('', cb)

    expect(() => unsubscribe()).not.toThrow()
    // Nao conta como inscrito "de verdade" pro reference-count: sozinho, unsubscribe fecha o ES
    // (mesmo ES ainda foi aberto pelo subscribe('') em si -- ver nota de implementacao no Step 3).
  })
})

describe('realLiveApi estado de conexao (subscribeConnection)', () => {
  it('onerror transitorio (readyState=CONNECTING) antes de 3s: sem transicao, segue live', () => {
    vi.useFakeTimers()
    subscribe('SNR-1', () => {})
    const es = MockEventSource.instances[0]
    const states: string[] = []
    subscribeConnection((s) => states.push(s))

    es.readyState = 0 // CONNECTING
    es.onerror?.()
    vi.advanceTimersByTime(2999)

    expect(states).toEqual(['live'])
  })

  it('onerror transitorio que persiste alem de 3s: transita para reconnecting', () => {
    vi.useFakeTimers()
    subscribe('SNR-1', () => {})
    const es = MockEventSource.instances[0]
    const states: string[] = []
    subscribeConnection((s) => states.push(s))

    es.readyState = 0 // CONNECTING
    es.onerror?.()
    vi.advanceTimersByTime(3000)

    expect(states).toEqual(['live', 'reconnecting'])
  })

  it('onopen durante o grace cancela o timer, permanece live (nao pisca)', () => {
    vi.useFakeTimers()
    subscribe('SNR-1', () => {})
    const es = MockEventSource.instances[0]
    const states: string[] = []
    subscribeConnection((s) => states.push(s))

    es.readyState = 0
    es.onerror?.()
    vi.advanceTimersByTime(1000)
    es.readyState = 1
    es.onopen?.()
    vi.advanceTimersByTime(5000)

    expect(states).toEqual(['live'])
  })

  it('onopen a partir de reconnecting: snap imediato para live, sem esperar grace', () => {
    vi.useFakeTimers()
    subscribe('SNR-1', () => {})
    const es = MockEventSource.instances[0]
    const states: string[] = []
    subscribeConnection((s) => states.push(s))

    es.readyState = 0
    es.onerror?.()
    vi.advanceTimersByTime(3000) // agora 'reconnecting'
    es.readyState = 1
    es.onopen?.()

    expect(states).toEqual(['live', 'reconnecting', 'live'])
  })

  it('onerror com readyState=CLOSED (2): vai direto para offline, ignorando o grace', () => {
    vi.useFakeTimers()
    subscribe('SNR-1', () => {})
    const es = MockEventSource.instances[0]
    const states: string[] = []
    subscribeConnection((s) => states.push(s))

    es.readyState = 2 // CLOSED
    es.onerror?.()

    expect(states).toEqual(['live', 'offline'])
  })

  it('subscribeConnection emite o estado atual na inscricao e cada transicao; unsubscribe para de receber', () => {
    vi.useFakeTimers()
    subscribe('SNR-1', () => {})
    const es = MockEventSource.instances[0]
    const states: string[] = []
    const unsub = subscribeConnection((s) => states.push(s))

    expect(states).toEqual(['live'])

    es.readyState = 2
    es.onerror?.()
    expect(states).toEqual(['live', 'offline'])

    unsub()
    es.readyState = 1
    es.onopen?.()
    expect(states).toEqual(['live', 'offline'])
  })

  it('source fecha (subscribers de dados a zero) com subscribeConnection ainda ativo; novo subscribe reabre e onopen notifica live', () => {
    vi.useFakeTimers()
    const unsubData = subscribe('SNR-1', () => {})
    const es1 = MockEventSource.instances[0]
    const states: string[] = []
    subscribeConnection((s) => states.push(s))

    // Cai numa reconexao real -> 'reconnecting'
    es1.readyState = 0 // CONNECTING
    es1.onerror?.()
    vi.advanceTimersByTime(3000)
    expect(states).toEqual(['live', 'reconnecting'])

    // Todo mundo que consumia dados sai: source fecha, mas o listener de
    // conexao (ex.: badge no Topbar/DashboardPage) segue inscrito.
    unsubData()
    expect(es1.closed).toBe(true)

    // Um novo subscribe() de dados reabre o EventSource compartilhado.
    subscribe('SNR-2', () => {})
    const es2 = MockEventSource.instances[1]

    // Ao conectar de fato, o listener pendurado DEVE ser notificado com 'live'
    // -- sem isso o badge trava mostrando 'reconnecting' pra sempre.
    es2.readyState = 1
    es2.onopen?.()

    expect(states).toEqual(['live', 'reconnecting', 'live'])
  })
})
