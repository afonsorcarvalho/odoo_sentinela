import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useLiveConnection } from './useLiveConnection'
import { liveApi } from './api'

afterEach(() => vi.restoreAllMocks())

describe('useLiveConnection', () => {
  it('retorna o estado atual reportado por liveApi.subscribeConnection', () => {
    const spy = vi.spyOn(liveApi, 'subscribeConnection').mockImplementation((cb) => {
      cb('live')
      return () => {}
    })
    const { result } = renderHook(() => useLiveConnection())
    expect(result.current).toBe('live')
    spy.mockRestore()
  })

  it('atualiza quando o listener recebe uma nova transicao', () => {
    let emit: (s: 'live' | 'reconnecting' | 'offline') => void = () => {}
    const spy = vi.spyOn(liveApi, 'subscribeConnection').mockImplementation((cb) => {
      emit = cb
      cb('live')
      return () => {}
    })
    const { result } = renderHook(() => useLiveConnection())
    expect(result.current).toBe('live')

    act(() => emit('reconnecting'))
    expect(result.current).toBe('reconnecting')

    act(() => emit('offline'))
    expect(result.current).toBe('offline')
    spy.mockRestore()
  })

  it('desinscreve no unmount', () => {
    const unsub = vi.fn()
    const spy = vi.spyOn(liveApi, 'subscribeConnection').mockImplementation((cb) => {
      cb('live')
      return unsub
    })
    const { unmount } = renderHook(() => useLiveConnection())
    expect(unsub).not.toHaveBeenCalled()
    unmount()
    expect(unsub).toHaveBeenCalledTimes(1)
    spy.mockRestore()
  })
})
