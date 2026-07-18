import { describe, it, expect } from 'vitest'
import { mockAuthApi } from './authApi'
import { decodeJwtExp } from '../../jwt'

describe('mockAuthApi', () => {
  it('admin/admin devolve token JWT-shaped (3 segmentos) com exp no futuro (~3600s a partir de agora)', async () => {
    const before = Date.now()
    const { access_token, token_type } = await mockAuthApi.login('admin', 'admin')
    const after = Date.now()
    expect(token_type).toBe('bearer')
    expect(access_token.split('.')).toHaveLength(3)
    const exp = decodeJwtExp(access_token)
    expect(exp).not.toBeNull()
    // exp deve estar entre before+3600s e after+3600s (tolerancia pro tempo de execucao do teste)
    expect(exp as number).toBeGreaterThanOrEqual(before + 3600_000 - 1000)
    expect(exp as number).toBeLessThanOrEqual(after + 3600_000 + 1000)
  })

  it('credencial errada rejeita', async () => {
    await expect(mockAuthApi.login('admin', 'errada')).rejects.toThrow()
  })

  it('usuario desconhecido rejeita', async () => {
    await expect(mockAuthApi.login('outro', 'admin')).rejects.toThrow()
  })
})
