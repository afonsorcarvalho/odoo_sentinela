import { describe, it, expect, vi, afterEach } from 'vitest'
import { isDemoMode } from './demoMode'

afterEach(() => vi.unstubAllEnvs())

describe('isDemoMode', () => {
  it('falso quando VITE_DEMO_MODE nao esta definido', () => {
    expect(isDemoMode()).toBe(false)
  })
})
