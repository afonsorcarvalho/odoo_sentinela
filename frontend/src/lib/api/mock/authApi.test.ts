import { describe, it, expect } from 'vitest'
import { mockAuthApi } from './authApi'
import { decodeJwtExp } from '../../jwt'

describe('mockAuthApi', () => {
  it('admin/admin devolve token JWT-shaped (3 segmentos) com exp no futuro (base fixa + 3600s)', async () => {
    const { access_token, token_type } = await mockAuthApi.login('admin', 'admin')
    expect(token_type).toBe('bearer')
    expect(access_token.split('.')).toHaveLength(3)
    expect(decodeJwtExp(access_token)).toBe((1_700_000_000 + 3600) * 1000)
  })

  it('credencial errada rejeita', async () => {
    await expect(mockAuthApi.login('admin', 'errada')).rejects.toThrow()
  })

  it('usuario desconhecido rejeita', async () => {
    await expect(mockAuthApi.login('outro', 'admin')).rejects.toThrow()
  })
})
