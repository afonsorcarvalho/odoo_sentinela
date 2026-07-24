import { describe, it, expect } from 'vitest'
import { buildChartOption, computeOutOfRangeBands } from './chartOption'
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
  it('historico vazio: cauda ao vivo NAO vira a serie (empty-state, nao cauda mascarando)', () => {
    const tail = [
      { sensor_code: 'S', ts: 5000, value: 20.1, alarm_state: 'ok' as const },
      { sensor_code: 'S', ts: 6000, value: 20.3, alarm_state: 'ok' as const },
    ]
    // history undefined -> histData vazio -> serie deve ficar vazia mesmo com cauda
    const opt = buildChartOption(undefined, t, undefined, undefined, tail) as any
    expect(opt.series[0].data).toEqual([])
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
    // itemStyle agora vive no item (nao mais na raiz do markArea) — ver Task 2.
    expect(markArea.data).toEqual([
      [
        { yAxis: 10, itemStyle: { color: 'var(--color-good-soft)', opacity: 0.5 }, emphasis: { disabled: true } },
        { yAxis: 20 },
      ],
    ])
  })
  it('sem threshold, series[0].markArea e undefined', () => {
    const option = buildChartOption(undefined, null)
    expect((option.series as any)[0].markArea).toBeUndefined()
  })
  it('usa a cor resolvida recebida no markArea, nao a custom property crua', () => {
    const opt = buildChartOption(hist, t, undefined, '#00ff00') as any
    // itemStyle agora vive no item (nao mais na raiz do markArea) — ver Task 2.
    expect(opt.series[0].markArea.data[0][0].itemStyle.color).toBe('#00ff00')
  })

  it('desenha faixa X vermelha quando a serie sai do limite', () => {
    const h: HistoryResponse = {
      sensor_code: 'S', window: '1h', resolution: 'raw',
      points: [{ ts: 0, value: 20 }, { ts: 100, value: 25 }, { ts: 200, value: 20 }],
    }
    const opt = buildChartOption(h, t) as any
    const areas = opt.series[0].markArea.data as any[]
    // primeiro item e a faixa verde em Y (yAxis); deve haver ao menos um item X (xAxis)
    const xBands = areas.filter((pair) => 'xAxis' in pair[0])
    expect(xBands.length).toBeGreaterThanOrEqual(1)
    expect(xBands[0][0].name).toMatch(/acima do limite/)
  })

  it('faixa verde de conformidade continua presente (primeiro item, em Y)', () => {
    const opt = buildChartOption(hist, t) as any
    const areas = opt.series[0].markArea.data as any[]
    expect('yAxis' in areas[0][0]).toBe(true)
  })

  it('labels das faixas ficam ocultas (so no hover): evita sopa de texto no topo', () => {
    // Regressao guarda: markArea renderiza o `name` de cada faixa como rotulo
    // permanente por padrao; com varias faixas viravam texto sobreposto. O
    // label fica desligado e so aparece no hover (emphasis).
    const h: HistoryResponse = {
      sensor_code: 'S', window: '1h', resolution: 'raw',
      points: [{ ts: 0, value: 20 }, { ts: 100, value: 25 }, { ts: 200, value: 20 }],
    }
    const opt = buildChartOption(h, t) as any
    expect(opt.series[0].markArea.label.show).toBe(false)
    expect(opt.series[0].markArea.emphasis.label.show).toBe(true)
  })

  it('desenha faixa de silencio quando now esta muito alem do ultimo ponto', () => {
    const opt = buildChartOption(hist, t, undefined, undefined, [], 2000 + 6 * 60_000) as any
    const areas = opt.series[0].markArea.data as any[]
    const silencio = areas.filter((pair) => 'xAxis' in pair[0] && pair[1].xAxis === 2000 + 6 * 60_000)
    expect(silencio).toHaveLength(1)
  })

  it('nao desenha faixa de silencio quando now esta perto do ultimo ponto', () => {
    const opt = buildChartOption(hist, t, undefined, undefined, [], 2000 + 60_000) as any
    const areas = (opt.series[0].markArea?.data ?? []) as any[]
    const silencio = areas.filter((pair) => 'xAxis' in pair[0] && pair[1].xAxis === 2000 + 60_000)
    expect(silencio).toHaveLength(0)
  })
})

const th: Threshold = { sensor_id: 'S', limite_min: 18, limite_max: 22, is_valor_padrao_regulatorio: true }

describe('computeOutOfRangeBands', () => {
  it('run contiguo acima do limite vira uma banda com direcao acima', () => {
    // espacamento mediano = 100
    const data: [number, number][] = [[0, 20], [100, 25], [200, 26], [300, 20]]
    const bandas = computeOutOfRangeBands(data, th)
    expect(bandas).toHaveLength(1)
    expect(bandas[0].direcao).toBe('acima')
    // banda cobre [100,200] estendida 1/2 ate os vizinhos dentro (50 e 250)
    expect(bandas[0].inicio).toBe(50)
    expect(bandas[0].fim).toBe(250)
  })

  it('run abaixo do limite vira banda com direcao abaixo', () => {
    const data: [number, number][] = [[0, 20], [100, 10], [200, 20]]
    const bandas = computeOutOfRangeBands(data, th)
    expect(bandas).toHaveLength(1)
    expect(bandas[0].direcao).toBe('abaixo')
  })

  it('troca de direcao sem passar por dentro fecha e abre nova banda', () => {
    // 25 (acima) -> 10 (abaixo): dois pontos fora, direcoes distintas
    const data: [number, number][] = [[0, 20], [100, 25], [200, 10], [300, 20]]
    const bandas = computeOutOfRangeBands(data, th)
    expect(bandas).toHaveLength(2)
    expect(bandas[0].direcao).toBe('acima')
    expect(bandas[1].direcao).toBe('abaixo')
  })

  it('ponto isolado fora do limite gera banda de largura positiva', () => {
    const data: [number, number][] = [[0, 20], [100, 25], [200, 20]]
    const bandas = computeOutOfRangeBands(data, th)
    expect(bandas).toHaveLength(1)
    expect(bandas[0].fim).toBeGreaterThan(bandas[0].inicio)
  })

  it('gap > 3x o espacamento mediano quebra a banda em duas', () => {
    // espacamento mediano = 100; salto de 100->1000 (gap 900 > 300)
    const data: [number, number][] = [[0, 25], [100, 25], [1000, 25], [1100, 25]]
    const bandas = computeOutOfRangeBands(data, th)
    expect(bandas).toHaveLength(2)
  })

  it('serie toda dentro do limite devolve []', () => {
    const data: [number, number][] = [[0, 19], [100, 20], [200, 21]]
    expect(computeOutOfRangeBands(data, th)).toEqual([])
  })

  it('threshold null devolve []', () => {
    const data: [number, number][] = [[0, 100], [100, 200]]
    expect(computeOutOfRangeBands(data, null)).toEqual([])
  })

  it('data vazia devolve []', () => {
    expect(computeOutOfRangeBands([], th)).toEqual([])
  })
})
