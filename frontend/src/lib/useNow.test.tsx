import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useNow } from './useNow'

afterEach(() => vi.useRealTimers())

describe('useNow', () => {
  it('emite tempos crescentes a cada intervalMs (sem novo LivePoint envolvido)', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useNow(1000))
    const first = result.current
    act(() => { vi.advanceTimersByTime(1000) })
    expect(result.current).toBeGreaterThan(first)
    const second = result.current
    act(() => { vi.advanceTimersByTime(1000) })
    expect(result.current).toBeGreaterThan(second)
  })

  it('usa 1 unico setInterval compartilhado entre multiplos assinantes do mesmo intervalMs', () => {
    vi.useFakeTimers()
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval')
    const { unmount: unmountA } = renderHook(() => useNow(1000))
    const { unmount: unmountB } = renderHook(() => useNow(1000))
    expect(setIntervalSpy).toHaveBeenCalledTimes(1)
    unmountA()
    unmountB()
    setIntervalSpy.mockRestore()
  })

  it('limpa o interval so quando o ULTIMO assinante desmonta', () => {
    vi.useFakeTimers()
    const clearIntervalSpy = vi.spyOn(globalThis, 'clearInterval')
    const { unmount: unmountA } = renderHook(() => useNow(2000))
    const { unmount: unmountB } = renderHook(() => useNow(2000))
    unmountA()
    expect(clearIntervalSpy).not.toHaveBeenCalled()
    unmountB()
    expect(clearIntervalSpy).toHaveBeenCalledTimes(1)
    clearIntervalSpy.mockRestore()
  })

  it('usa Date.now() como valor inicial (nao espera o 1o tick)', () => {
    vi.useFakeTimers()
    vi.setSystemTime(123_456_789)
    const { result } = renderHook(() => useNow(1000))
    expect(result.current).toBe(123_456_789)
  })
})
