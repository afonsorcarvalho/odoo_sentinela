import { describe, it, expect } from 'vitest'
import { mockReportApi } from './reportApi'

describe('mockReportApi', () => {
  it('inicio == fim -> 24 buckets por hora, com sem_dados e fora_limite', async () => {
    const r = await mockReportApi.getReport({ sensores: ['TEMP-EXP-01'], inicio: '2026-01-10', fim: '2026-01-10' })
    expect(r.granularidade).toBe('hora')
    const b = r.sensores[0].buckets
    expect(b).toHaveLength(24)
    expect(b[0].bucket).toBe('2026-01-10T00:00:00-03:00')
    expect(b.some((x) => x.estado === 'sem_dados')).toBe(true)
    expect(b.some((x) => x.fora_limite)).toBe(true)
  })
  it('periodo de 31 dias -> dia; mais de 62 dias -> mes', async () => {
    const d = await mockReportApi.getReport({ sensores: ['TEMP-EXP-01'], inicio: '2026-01-01', fim: '2026-01-31' })
    expect(d.granularidade).toBe('dia')
    expect(d.sensores[0].buckets).toHaveLength(31)
    const m = await mockReportApi.getReport({ sensores: ['TEMP-EXP-01'], inicio: '2026-01-01', fim: '2026-06-30' })
    expect(m.granularidade).toBe('mes')
    expect(m.sensores[0].buckets).toHaveLength(6)
  })
  it('PDF devolve Blob', async () => {
    const blob = await mockReportApi.getReportPdf({ sensores: ['TEMP-EXP-01'], inicio: '2026-01-01', fim: '2026-01-01' })
    expect(blob).toBeInstanceOf(Blob)
  })
})
