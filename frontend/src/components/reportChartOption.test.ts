import { describe, it, expect } from 'vitest'
import { buildReportChartOption } from './reportChartOption'
import type { ReportSensor } from '../lib/api/contracts'

const sensor = (limites: ReportSensor['limites']): ReportSensor => ({
  sensor_code: 'S1', nome: 'Sensor 1', unidade: '°C', site: null, limites,
  alteracoes_limite: [], alarmes: [],
  buckets: [
    { bucket: '2026-01-10T00:00:00-03:00', avg: 20, min: 18, max: 22, n_ok: 60, n_falha: 0, estado: 'ok', fora_limite: false },
    { bucket: '2026-01-10T01:00:00-03:00', avg: null, min: null, max: null, n_ok: 0, n_falha: 5, estado: 'falha_instrumento', fora_limite: false },
    { bucket: '2026-01-10T02:00:00-03:00', avg: null, min: null, max: null, n_ok: 0, n_falha: 0, estado: 'sem_dados', fora_limite: false },
  ],
})

type S = { name?: string; data: unknown[]; connectNulls?: boolean; markLine?: { data: unknown[] } }
const series = (o: ReturnType<typeof buildReportChartOption>) => o.series as S[]

describe('buildReportChartOption', () => {
  it('avg null onde estado != ok, com connectNulls false', () => {
    const avg = series(buildReportChartOption(sensor(null), 'hora')).find((s) => s.name === 'Média')!
    expect(avg.data).toEqual([20, null, null])
    expect(avg.connectNulls).toBe(false)
  })
  it('area min-max: stack de min e max-min', () => {
    const s = series(buildReportChartOption(sensor(null), 'hora'))
    expect(s.find((x) => x.name === 'min')!.data).toEqual([18, null, null])
    expect(s.find((x) => x.name === 'faixa')!.data).toEqual([4, null, null])
  })
  it('rotulos do eixo: hora -> HH:MM', () => {
    const o = buildReportChartOption(sensor(null), 'hora')
    expect((o.xAxis as { data: string[] }).data[1]).toBe('01:00')
  })
  it('sem markLine com limites null; com limites, uma linha por limite', () => {
    expect(series(buildReportChartOption(sensor(null), 'hora')).some((s) => s.markLine)).toBe(false)
    const avg = series(buildReportChartOption(sensor({ limite_min: 10, limite_max: 30 }), 'hora')).find((s) => s.name === 'Média')!
    expect(avg.markLine!.data).toHaveLength(2)
  })
})
