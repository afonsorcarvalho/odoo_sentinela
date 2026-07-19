import { describe, it, expect } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useSensorMeta, useThreshold, useHistory, useSensors, useThresholds, useAlarms, useConfig, useSaveLayout } from './queries'
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

  it('useSensors lista os 5 sensores', async () => {
    const { result } = renderHook(() => useSensors(), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.map((s) => s.sensor_code).sort()).toEqual([
      'PRESS-EXP-01', 'PRESS-PRE-01', 'TEMP-ARS-01', 'TEMP-EXP-01', 'TEMP-PRE-01',
    ])
  })

  it('useThresholds devolve um resultado por codigo, na mesma ordem', async () => {
    const { result } = renderHook(
      () => useThresholds(['TEMP-EXP-01', 'TEMP-ARS-01']),
      { wrapper: wrapper() },
    )
    await waitFor(() => expect(result.current.every((r) => r.isSuccess)).toBe(true))
    expect(result.current[0].data?.limite_max).toBe(22)
    expect(result.current[1].data).toBeNull() // Arsenal, sem threshold
  })

  it('useAlarms carrega a lista de alarmes do mock', async () => {
    const { result } = renderHook(() => useAlarms(), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.length).toBeGreaterThan(0)
  })

  it('useConfig carrega o intervalo do carrossel do mock', async () => {
    const { result } = renderHook(() => useConfig(), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.carousel_interval_ms).toBe(4000)
  })

  it('useSaveLayout chama saveLayout e resolve', async () => {
    const layout = { version: 1 as const, grid: { cols: 12, rowHeight: 40, margin: [8, 8] as [number, number] }, widgets: [] }
    const { result } = renderHook(() => useSaveLayout(), { wrapper: wrapper() })
    result.current.mutate(layout)
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
  })
})
