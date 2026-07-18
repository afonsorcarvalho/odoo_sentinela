import { describe, it, expect } from 'vitest'
import { buildChartOption } from './chartOption'
import type { HistoryResponse, Threshold } from '../lib/types'

const t: Threshold = { sensor_id: 'S', limite_min: 18, limite_max: 22, is_valor_padrao_regulatorio: true }
const hist: HistoryResponse = {
  sensor_code: 'S', window: '1h', resolution: 'raw',
  points: [{ ts: 1000, value: 19 }, { ts: 2000, value: 21 }],
}

describe('buildChartOption', () => {
  it('markLines batem com os limites do threshold', () => {
    const opt = buildChartOption(hist, t) as any
    const marks = opt.series[0].markLine.data.map((d: any) => d.yAxis)
    expect(marks).toContain(18)
    expect(marks).toContain(22)
  })
  it('serie base tem os pontos do historico', () => {
    const opt = buildChartOption(hist, t) as any
    expect(opt.series[0].data).toEqual([[1000, 19], [2000, 21]])
  })
  it('sem threshold nao desenha markLine', () => {
    const opt = buildChartOption(hist, null) as any
    expect(opt.series[0].markLine).toBeUndefined()
  })
  it('sem historico devolve serie vazia', () => {
    const opt = buildChartOption(undefined, t) as any
    expect(opt.series[0].data).toEqual([])
  })
  it('resolucao agg usa o avg de cada ponto (min/max ignorados na serie)', () => {
    const aggHist: HistoryResponse = {
      sensor_code: 'S', window: '30d', resolution: 'agg',
      points: [{ ts: 1000, min: 17, max: 23, avg: 20 }, { ts: 2000, min: 18, max: 24, avg: 21 }],
    }
    const opt = buildChartOption(aggHist, t) as any
    expect(opt.series[0].data).toEqual([[1000, 20], [2000, 21]])
  })
  it('usa a cor resolvida recebida no markLine, nao a custom property crua', () => {
    const opt = buildChartOption(hist, t, '#ff0000') as any
    expect(opt.series[0].markLine.lineStyle.color).toBe('#ff0000')
  })
  it('sem cor explicita cai no default var(--color-crit) (compat)', () => {
    const opt = buildChartOption(hist, t) as any
    expect(opt.series[0].markLine.lineStyle.color).toBe('var(--color-crit)')
  })
})
