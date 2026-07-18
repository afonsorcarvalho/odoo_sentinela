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
})
