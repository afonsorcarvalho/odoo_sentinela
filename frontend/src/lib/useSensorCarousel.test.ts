import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useSensorCarousel } from './useSensorCarousel'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('useSensorCarousel', () => {
  it('nao avanca sozinho quando count <= 1', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useSensorCarousel(1))
    act(() => {
      vi.advanceTimersByTime(10000)
    })
    expect(result.current.activeIndex).toBe(0)
  })

  it('avanca activeIndex a cada intervalMs, ciclando', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useSensorCarousel(3, 3000))
    expect(result.current.activeIndex).toBe(0)
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(result.current.activeIndex).toBe(1)
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(result.current.activeIndex).toBe(2)
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(result.current.activeIndex).toBe(0)
  })

  it('pause() para o avanco; resume() reinicia o ciclo do zero', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useSensorCarousel(2, 3000))
    act(() => {
      result.current.pause()
    })
    act(() => {
      vi.advanceTimersByTime(10000)
    })
    expect(result.current.activeIndex).toBe(0)
    act(() => {
      result.current.resume()
    })
    act(() => {
      vi.advanceTimersByTime(2999)
    })
    expect(result.current.activeIndex).toBe(0)
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(result.current.activeIndex).toBe(1)
  })

  it('setActiveIndex troca na hora e reinicia o timer de 3s', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useSensorCarousel(3, 3000))
    act(() => {
      vi.advanceTimersByTime(2000)
    })
    act(() => {
      result.current.setActiveIndex(2)
    })
    expect(result.current.activeIndex).toBe(2)
    act(() => {
      vi.advanceTimersByTime(2000)
    })
    expect(result.current.activeIndex).toBe(2)
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(result.current.activeIndex).toBe(0)
  })

  it('prefers-reduced-motion: reduce -> nao avanca sozinho', () => {
    vi.useFakeTimers()
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockReturnValue({
        matches: true,
        media: '(prefers-reduced-motion: reduce)',
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    )
    const { result } = renderHook(() => useSensorCarousel(3, 3000))
    act(() => {
      vi.advanceTimersByTime(9000)
    })
    expect(result.current.activeIndex).toBe(0)
  })
})
