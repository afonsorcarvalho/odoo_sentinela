import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'

const setOption = vi.fn()
const appendData = vi.fn()
const dispose = vi.fn()
vi.mock('echarts', () => ({
  init: () => ({ setOption, appendData, dispose, resize: vi.fn() }),
}))

import { TimeSeriesChart } from './TimeSeriesChart'
import type { HistoryResponse, Threshold, LivePoint } from '../lib/types'

const t: Threshold = { sensor_id: 'S', limite_min: 18, limite_max: 22, is_valor_padrao_regulatorio: true }
const hist: HistoryResponse = { sensor_code: 'S', window: '1h', resolution: 'raw', points: [{ ts: 1000, value: 20 }] }

beforeEach(() => { setOption.mockClear(); appendData.mockClear(); dispose.mockClear() })

describe('TimeSeriesChart', () => {
  it('setOption uma vez com o historico; ponto ao vivo usa appendData, NAO setOption de novo', () => {
    const { rerender } = render(<TimeSeriesChart history={hist} threshold={t} tail={[]} />)
    const optionCallsAfterHistory = setOption.mock.calls.length
    expect(optionCallsAfterHistory).toBeGreaterThanOrEqual(1)

    const p: LivePoint = { sensor_code: 'S', ts: 2000, value: 21, alarm_state: 'ok' }
    rerender(<TimeSeriesChart history={hist} threshold={t} tail={[p]} />)

    expect(appendData).toHaveBeenCalledTimes(1)              // anexou o ponto
    expect(setOption.mock.calls.length).toBe(optionCallsAfterHistory) // NAO refez a serie base
  })

  it('so anexa os pontos NOVOS da cauda (cursor), nao reenvia os ja anexados', () => {
    const { rerender } = render(<TimeSeriesChart history={hist} threshold={t} tail={[]} />)

    const p1: LivePoint = { sensor_code: 'S', ts: 2000, value: 21, alarm_state: 'ok' }
    rerender(<TimeSeriesChart history={hist} threshold={t} tail={[p1]} />)
    expect(appendData).toHaveBeenCalledTimes(1)

    const p2: LivePoint = { sensor_code: 'S', ts: 3000, value: 22, alarm_state: 'ok' }
    rerender(<TimeSeriesChart history={hist} threshold={t} tail={[p1, p2]} />)
    expect(appendData).toHaveBeenCalledTimes(2) // so p2 foi anexado, p1 nao foi reenviado
    expect(appendData).toHaveBeenLastCalledWith({ seriesIndex: 0, data: [[3000, 22]] })
  })

  it('faz dispose do chart ao desmontar', () => {
    const { unmount } = render(<TimeSeriesChart history={hist} threshold={t} tail={[]} />)
    unmount()
    expect(dispose).toHaveBeenCalledTimes(1)
  })

  it('continua anexando apos o buffer da cauda estourar o teto e pontos antigos saírem pela frente (useLiveTail desliza)', () => {
    // Simula o comportamento de useLiveTail: array de tamanho fixo (cap),
    // onde a chegada de um ponto novo empurra o mais antigo para fora pela
    // frente (slice). O comprimento do array (tail.length) fica constante
    // apos o cap ser atingido — um cursor baseado em length trava aqui.
    const cap = 300
    const makePoint = (ts: number): LivePoint => ({ sensor_code: 'S', ts, value: 20, alarm_state: 'ok' })
    const tailAtCap: LivePoint[] = Array.from({ length: cap }, (_, i) => makePoint(1000 + i)) // ts 1000..1299

    const { rerender } = render(<TimeSeriesChart history={hist} threshold={t} tail={tailAtCap} />)
    appendData.mockClear()

    // Novo ponto chega (ts 1300): useLiveTail descarta o mais antigo (ts 1000)
    // e mantem o length em `cap`. tail.length antes e depois: ambos `cap`.
    const slidTail: LivePoint[] = [...tailAtCap.slice(1), makePoint(1000 + cap)]
    expect(slidTail.length).toBe(tailAtCap.length) // length nao mudou (cursor por length trava aqui)

    rerender(<TimeSeriesChart history={hist} threshold={t} tail={slidTail} />)

    // O ponto mais novo (ts 1300) deve ter sido anexado mesmo com length constante.
    expect(appendData).toHaveBeenCalledTimes(1)
    expect(appendData).toHaveBeenLastCalledWith({ seriesIndex: 0, data: [[1000 + cap, 20]] })
  })

  it('faz trim ocasional (setOption) ao ultrapassar MAX_LIVE_POINTS, mantendo a serie limitada', () => {
    const cap = 300
    const makePoint = (ts: number): LivePoint => ({ sensor_code: 'S', ts, value: 20, alarm_state: 'ok' })
    let tail: LivePoint[] = Array.from({ length: cap }, (_, i) => makePoint(1 + i)) // ts 1..300

    const { rerender } = render(<TimeSeriesChart history={hist} threshold={t} tail={tail} />)
    const optionCallsAfterHistory = setOption.mock.calls.length

    // Avanca a cauda deterministicamente, um ponto novo por vez, ate passar
    // de MAX_LIVE_POINTS (600) pontos ao vivo anexados desde a serie base.
    const MAX_LIVE_POINTS = 600
    let nextTs = cap + 1
    for (let i = 0; i < MAX_LIVE_POINTS + 5; i++) {
      tail = [...tail.slice(1), makePoint(nextTs)]
      nextTs += 1
      rerender(<TimeSeriesChart history={hist} threshold={t} tail={tail} />)
    }

    // O rebuild ocasional (setOption) deve ter acontecido pelo menos uma vez
    // alem da chamada inicial da serie base.
    expect(setOption.mock.calls.length).toBeGreaterThan(optionCallsAfterHistory)
  })
})
