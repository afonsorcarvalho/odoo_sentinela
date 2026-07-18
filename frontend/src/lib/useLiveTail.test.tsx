import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useLiveTail } from './useLiveTail'
import { liveApi } from './api'

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
    expect(result.current.tail.length).toBe(3)
  })
  it('chama unsubscribe no unmount (sem vazar timer)', () => {
    const unsub = vi.fn()
    const spy = vi.spyOn(liveApi, 'subscribe').mockReturnValue(unsub)
    const { unmount } = renderHook(() => useLiveTail('x'))
    expect(unsub).not.toHaveBeenCalled()
    unmount()
    expect(unsub).toHaveBeenCalledTimes(1)
    spy.mockRestore()
  })
})
