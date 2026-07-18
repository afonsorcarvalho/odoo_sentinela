import { describe, it, expect, vi, afterEach } from 'vitest'
import { realAuthApi } from './authApi'

afterEach(() => vi.unstubAllGlobals())

describe('realAuthApi', () => {
  it('POST /auth/login com body {usuario,senha}, devolve o JSON da resposta em sucesso', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: 'abc.def.ghi', token_type: 'bearer' }),
    })
    vi.stubGlobal('fetch', mockFetch)

    const result = await realAuthApi.login('admin', 'admin')

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/auth/login'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ usuario: 'admin', senha: 'admin' }),
      }),
    )
    expect(result).toEqual({ access_token: 'abc.def.ghi', token_type: 'bearer' })
  })

  it('resposta nao-ok (ex: 401) lanca erro', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) }))
    await expect(realAuthApi.login('admin', 'errada')).rejects.toThrow()
  })
})
