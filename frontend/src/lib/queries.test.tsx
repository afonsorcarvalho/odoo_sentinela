import { describe, it, expect } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useSensorMeta, useThreshold, useHistory } from './queries'
import type { ReactNode } from 'react'

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('queries', () => {
  it('useSensorMeta carrega a fixture', async () => {
    const { result } = renderHook(() => useSensorMeta('TEMP-EXP-01'), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.sensor_code).toBe('TEMP-EXP-01')
  })
  it('useHistory 1h = raw', async () => {
    const { result } = renderHook(() => useHistory('x', '1h'), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.resolution).toBe('raw')
  })
  it('useThreshold carrega limites', async () => {
    const { result } = renderHook(() => useThreshold('TEMP-EXP-01'), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.limite_max).toBe(22)
  })
})
