import { describe, it, expect, vi, afterEach } from 'vitest'
import { isDemoMode } from './demoMode'

afterEach(() => vi.unstubAllEnvs())

describe('isDemoMode', () => {
  it('falso quando VITE_DEMO_MODE nao esta definido', () => {
    expect(isDemoMode()).toBe(false)
  })

  it('verdadeiro com DEMO=true e API mock', () => {
    vi.stubEnv('VITE_DEMO_MODE', 'true')
    vi.stubEnv('VITE_API_MODE', 'mock')
    expect(isDemoMode()).toBe(true)
  })

  it('FALSO com DEMO=true mas API real (banner nao pode mentir sobre dados reais)', () => {
    vi.stubEnv('VITE_DEMO_MODE', 'true')
    vi.stubEnv('VITE_API_MODE', 'real')
    expect(isDemoMode()).toBe(false)
  })
})
