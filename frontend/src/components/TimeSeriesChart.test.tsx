import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'

const setOption = vi.fn()
const dispose = vi.fn()
vi.mock('echarts', () => ({
  init: () => ({ setOption, dispose, resize: vi.fn() }),
}))

import { TimeSeriesChart } from './TimeSeriesChart'
import type { HistoryResponse, Threshold, LivePoint } from '../lib/types'

const t: Threshold = { sensor_id: 'S', limite_min: 18, limite_max: 22, is_valor_padrao_regulatorio: true }
const hist: HistoryResponse = { sensor_code: 'S', window: '1h', resolution: 'raw', points: [{ ts: 1000, value: 20 }] }

// Extrai os dados da serie do ultimo setOption aplicado.
function lastSeriesData(): [number, number][] {
  const opt = setOption.mock.calls[setOption.mock.calls.length - 1][0]
  return opt.series[0].data
}

beforeEach(() => { setOption.mockClear(); dispose.mockClear() })

describe('TimeSeriesChart', () => {
  it('desenha a serie historica via setOption', () => {
    render(<TimeSeriesChart history={hist} threshold={t} tail={[]} />)
    expect(setOption).toHaveBeenCalled()
    expect(lastSeriesData()).toEqual([[1000, 20]])
  })

  it('anexa a cauda ao vivo localmente na serie (historico + cauda), sem appendData', () => {
    const { rerender } = render(<TimeSeriesChart history={hist} threshold={t} tail={[]} />)
    const p: LivePoint = { sensor_code: 'S', ts: 2000, value: 21, alarm_state: 'ok' }
    rerender(<TimeSeriesChart history={hist} threshold={t} tail={[p]} />)
    // A serie desenhada agora contem o ponto historico E o ponto ao vivo.
    expect(lastSeriesData()).toEqual([[1000, 20], [2000, 21]])
  })

  it('mais pontos ao vivo continuam sendo anexados (cauda deslizante nao trava o desenho)', () => {
    // Simula useLiveTail deslizando: o mais antigo sai pela frente, o novo entra.
    const p1: LivePoint = { sensor_code: 'S', ts: 2000, value: 21, alarm_state: 'ok' }
    const p2: LivePoint = { sensor_code: 'S', ts: 3000, value: 19, alarm_state: 'ok' }
    const { rerender } = render(<TimeSeriesChart history={hist} threshold={t} tail={[p1]} />)
    rerender(<TimeSeriesChart history={hist} threshold={t} tail={[p1, p2]} />)
    expect(lastSeriesData()).toEqual([[1000, 20], [2000, 21], [3000, 19]])
  })

  it('faz dispose do chart ao desmontar', () => {
    const { unmount } = render(<TimeSeriesChart history={hist} threshold={t} tail={[]} />)
    unmount()
    expect(dispose).toHaveBeenCalledTimes(1)
  })
})
