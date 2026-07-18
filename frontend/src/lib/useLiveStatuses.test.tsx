import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useLiveStatuses } from './useLiveStatuses'
import { liveApi } from './api'

afterEach(() => vi.useRealTimers())

describe('useLiveStatuses', () => {
  it('acumula o ultimo ponto por sensor_code', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useLiveStatuses(['TEMP-EXP-01', 'TEMP-PRE-01']))
    act(() => { vi.advanceTimersByTime(2500) })
    expect(result.current['TEMP-EXP-01']).toBeDefined()
    expect(result.current['TEMP-PRE-01']).toBeDefined()
    expect(result.current['TEMP-EXP-01'].sensor_code).toBe('TEMP-EXP-01')
  })

  it('chama unsubscribe de TODOS os codigos no unmount (nao vaza timer)', () => {
    const unsubs = [vi.fn(), vi.fn()]
    let call = 0
    const spy = vi.spyOn(liveApi, 'subscribe').mockImplementation(() => unsubs[call++])
    const { unmount } = renderHook(() => useLiveStatuses(['TEMP-EXP-01', 'TEMP-PRE-01']))
    expect(unsubs[0]).not.toHaveBeenCalled()
    expect(unsubs[1]).not.toHaveBeenCalled()
    unmount()
    expect(unsubs[0]).toHaveBeenCalledTimes(1)
    expect(unsubs[1]).toHaveBeenCalledTimes(1)
    spy.mockRestore()
  })

  it('nao re-assina quando `codes` muda de referencia mas mantem o mesmo conteudo', () => {
    const spy = vi.spyOn(liveApi, 'subscribe')
    const { rerender } = renderHook(({ codes }) => useLiveStatuses(codes), {
      initialProps: { codes: ['TEMP-EXP-01', 'TEMP-PRE-01'] },
    })
    const callsAfterFirst = spy.mock.calls.length
    rerender({ codes: ['TEMP-EXP-01', 'TEMP-PRE-01'] }) // novo array, mesmo conteudo
    expect(spy.mock.calls.length).toBe(callsAfterFirst) // nao re-assinou
    spy.mockRestore()
  })

  it('re-assina quando o CONTEUDO de `codes` muda', () => {
    const spy = vi.spyOn(liveApi, 'subscribe')
    const { rerender } = renderHook(({ codes }) => useLiveStatuses(codes), {
      initialProps: { codes: ['TEMP-EXP-01'] },
    })
    const callsAfterFirst = spy.mock.calls.length
    rerender({ codes: ['TEMP-EXP-01', 'TEMP-ARS-01'] })
    expect(spy.mock.calls.length).toBeGreaterThan(callsAfterFirst)
    spy.mockRestore()
  })
})
