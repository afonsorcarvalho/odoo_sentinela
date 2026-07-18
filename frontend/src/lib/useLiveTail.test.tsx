import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useLiveTail } from './useLiveTail'

afterEach(() => vi.useRealTimers())

describe('useLiveTail', () => {
  it('acumula pontos incrementais', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useLiveTail('x'))
    expect(result.current.tail.length).toBe(0)
    act(() => { vi.advanceTimersByTime(3000) })
    expect(result.current.tail.length).toBeGreaterThanOrEqual(2)
    expect(result.current.last).not.toBeNull()
  })
  it('respeita o cap max', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useLiveTail('x', 3))
    act(() => { vi.advanceTimersByTime(10000) })
    expect(result.current.tail.length).toBeLessThanOrEqual(3)
  })
  it('desinscreve no unmount (nao vaza timer)', () => {
    vi.useFakeTimers()
    const { result, unmount } = renderHook(() => useLiveTail('x'))
    act(() => { vi.advanceTimersByTime(2000) })
    const n = result.current.tail.length
    unmount()
    act(() => { vi.advanceTimersByTime(5000) })
    expect(result.current.tail.length).toBe(n)
  })
})
