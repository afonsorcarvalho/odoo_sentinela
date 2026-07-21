import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useCountUp } from './useCountUp'

// rAF determinístico via fake timers: cada "frame" avança performance.now.
function installRaf() {
  let now = 0
  vi.spyOn(performance, 'now').mockImplementation(() => now)
  vi.stubGlobal(
    'requestAnimationFrame',
    (cb: FrameRequestCallback) => setTimeout(() => { now += 16; cb(now) }, 16) as unknown as number,
  )
  vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id))
}

describe('useCountUp', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('interpola do valor anterior ate o alvo', () => {
    vi.useFakeTimers()
    installRaf()
    const { result, rerender } = renderHook(({ v }) => useCountUp(v, { durationMs: 100 }), {
      initialProps: { v: 0 as number | null },
    })
    expect(result.current).toBe(0)
    rerender({ v: 10 })
    act(() => { vi.advanceTimersByTime(50) })
    expect(result.current).toBeGreaterThan(0)
    expect(result.current).toBeLessThan(10)
    act(() => { vi.advanceTimersByTime(100) })
    expect(result.current).toBe(10)
    vi.useRealTimers()
  })

  it('prefers-reduced-motion: retorna o alvo direto sem animar', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockReturnValue({
        matches: true,
        media: '(prefers-reduced-motion: reduce)',
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    )
    const { result, rerender } = renderHook(({ v }) => useCountUp(v), {
      initialProps: { v: 0 as number | null },
    })
    rerender({ v: 42 })
    expect(result.current).toBe(42)
  })

  it('propaga null', () => {
    const { result } = renderHook(() => useCountUp(null))
    expect(result.current).toBeNull()
  })
})
