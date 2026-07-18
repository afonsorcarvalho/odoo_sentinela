import { describe, it, expect } from 'vitest'
import { metaApi, historyApi, liveApi, authApi, alarmApi } from './index'

// Em teste, VITE_API_MODE e forcado para 'mock' (vite.config.ts) — este teste
// so confirma que o barril exporta todos os adapters exigidos pelo app.
describe('api barrel', () => {
  it('exporta os 5 adapters', () => {
    expect(metaApi).toBeDefined()
    expect(historyApi).toBeDefined()
    expect(liveApi).toBeDefined()
    expect(authApi).toBeDefined()
    expect(alarmApi).toBeDefined()
  })
})
