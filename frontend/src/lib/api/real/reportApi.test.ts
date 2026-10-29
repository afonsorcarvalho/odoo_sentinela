import { describe, it, expect, vi, afterEach } from 'vitest'
import { realReportApi } from './reportApi'
import { TOKEN_STORAGE_KEY } from '../../useAuth'

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

const params = { sensores: ['A', 'B'], inicio: '2026-01-01', fim: '2026-01-31' }
const qs = 'sensores=A%2CB&inicio=2026-01-01&fim=2026-01-31'

describe('realReportApi', () => {
  it('getReport chama GET /relatorio com Bearer e devolve o JSON', async () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'tok')
    const body = { granularidade: 'dia', sensores: [] }
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => body })
    vi.stubGlobal('fetch', mockFetch)

    const r = await realReportApi.getReport(params)

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining(`/relatorio?${qs}`),
      { headers: { Authorization: 'Bearer tok' } },
    )
    expect(r).toEqual(body)
  })

  it('getReportPdf chama GET /relatorio.pdf com Bearer e devolve o Blob', async () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'tok')
    const blob = new Blob(['%PDF'], { type: 'application/pdf' })
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, blob: async () => blob })
    vi.stubGlobal('fetch', mockFetch)

    const r = await realReportApi.getReportPdf(params)

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining(`/relatorio.pdf?${qs}`),
      { headers: { Authorization: 'Bearer tok' } },
    )
    expect(r).toBe(blob)
  })

  it('422 expoe o detail da API como mensagem legivel', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false, status: 422, json: async () => ({ detail: 'período máximo de 366 dias' }),
    })
    vi.stubGlobal('fetch', mockFetch)

    await expect(realReportApi.getReport(params)).rejects.toThrow('período máximo de 366 dias')
    await expect(realReportApi.getReportPdf(params)).rejects.toThrow('período máximo de 366 dias')
  })

  it('erro sem detail legivel cai na mensagem generica', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }))
    await expect(realReportApi.getReport(params)).rejects.toThrow(/erro 500/)
  })
})
