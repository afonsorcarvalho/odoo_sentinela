import { describe, it, expect, vi, afterEach } from 'vitest'
import { authFetchJson } from './http'
import { TOKEN_STORAGE_KEY } from '../../useAuth'

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('authFetchJson', () => {
  it('inclui Authorization: Bearer quando ha token em localStorage', async () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'abc.def.ghi')
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ foo: 'bar' }) })
    vi.stubGlobal('fetch', mockFetch)

    const result = await authFetchJson('/sensores/SNR-1')

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/sensores/SNR-1'),
      { headers: { Authorization: 'Bearer abc.def.ghi' } },
    )
    expect(result).toEqual({ foo: 'bar' })
  })

  it('sem token em localStorage, chama sem header Authorization', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
    vi.stubGlobal('fetch', mockFetch)

    await authFetchJson('/sensores')

    expect(mockFetch).toHaveBeenCalledWith(expect.any(String), { headers: {} })
  })

  it('resposta nao-ok lanca erro', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({}) }))
    await expect(authFetchJson('/sensores/SNR-X')).rejects.toThrow()
  })
})
