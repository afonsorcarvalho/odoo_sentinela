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
  it('sem historico devolve serie vazia (e eixo Y ainda contem os limites, sem NaN)', () => {
    const opt = buildChartOption(undefined, t) as any
    expect(opt.series[0].data).toEqual([])
    expect(opt.yAxis.min).toBeLessThanOrEqual(18)
    expect(opt.yAxis.max).toBeGreaterThanOrEqual(22)
    expect(Number.isNaN(opt.yAxis.min)).toBe(false)
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
  it('anexa a cauda ao vivo apos o historico (so pontos mais novos que o ultimo ts do historico)', () => {
    const tail = [
      { sensor_code: 'S', ts: 1500, value: 20.5, alarm_state: 'ok' as const }, // <= ultimo hist (2000): ignorado
      { sensor_code: 'S', ts: 2500, value: 20.8, alarm_state: 'ok' as const }, // novo: anexado
      { sensor_code: 'S', ts: 3000, value: 21.2, alarm_state: 'ok' as const },
    ]
    const opt = buildChartOption(hist, t, '#ff0000', 'var(--color-good-soft)', tail) as any
    expect(opt.series[0].data).toEqual([[1000, 19], [2000, 21], [2500, 20.8], [3000, 21.2]])
  })
  it('estende o eixo Y para conter as linhas de limite (senao ficariam clipadas)', () => {
    const opt = buildChartOption(hist, t) as any
    // faixa 18..22; dados 19..21 dentro. eixo deve conter 18 e 22 com folga.
    expect(opt.yAxis.min).toBeLessThanOrEqual(18)
    expect(opt.yAxis.max).toBeGreaterThanOrEqual(22)
  })
  it('estende o eixo Y tambem para um valor lido fora da faixa', () => {
    const outHist: HistoryResponse = {
      sensor_code: 'S', window: '1h', resolution: 'raw',
      points: [{ ts: 1000, value: 25 }], // acima do limite_max 22
    }
    const opt = buildChartOption(outHist, t) as any
    expect(opt.yAxis.max).toBeGreaterThanOrEqual(25)
  })
  it('com threshold, series[0].markArea cobre limite_min..limite_max', () => {
    const threshold = { sensor_id: 'A', limite_min: 10, limite_max: 20, is_valor_padrao_regulatorio: false }
    const option = buildChartOption(undefined, threshold)
    const markArea = (option.series as any)[0].markArea
    expect(markArea.data).toEqual([[{ yAxis: 10 }, { yAxis: 20 }]])
  })
  it('sem threshold, series[0].markArea e undefined', () => {
    const option = buildChartOption(undefined, null)
    expect((option.series as any)[0].markArea).toBeUndefined()
  })
  it('usa a cor resolvida recebida no markArea, nao a custom property crua', () => {
    const opt = buildChartOption(hist, t, undefined, '#00ff00') as any
    expect(opt.series[0].markArea.itemStyle.color).toBe('#00ff00')
  })
})
