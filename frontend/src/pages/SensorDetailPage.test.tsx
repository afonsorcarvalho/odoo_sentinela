import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

// ECharts mockado (sem canvas em jsdom)
vi.mock('echarts', () => ({ init: () => ({ setOption: vi.fn(), appendData: vi.fn(), dispose: vi.fn(), resize: vi.fn() }) }))

import { SensorDetailPage } from './SensorDetailPage'
import * as api from '../lib/api'

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{node}</QueryClientProvider>
}

afterEach(() => vi.useRealTimers())

describe('SensorDetailPage', () => {
  it('renderiza nome do sensor, readout e faixa', async () => {
    render(wrap(<SensorDetailPage code="TEMP-EXP-01" />))
    await waitFor(() => expect(screen.getByText(/Temperatura — Expurgo/)).toBeInTheDocument())
    expect(screen.getByText(/Faixa segura/)).toBeInTheDocument()
  })

  it('trocar janela dispara novo fetch de historico (getHistory chamado de novo)', async () => {
    const spy = vi.spyOn(api.historyApi, 'getHistory')
    render(wrap(<SensorDetailPage code="TEMP-EXP-01" />))
    await waitFor(() => expect(spy).toHaveBeenCalledWith('TEMP-EXP-01', '24h'))
    const before = spy.mock.calls.length
    await userEvent.click(screen.getByRole('button', { name: '7d' }))
    await waitFor(() => expect(spy).toHaveBeenCalledWith('TEMP-EXP-01', '7d'))
    expect(spy.mock.calls.length).toBeGreaterThan(before)
    spy.mockRestore()
  })

  it('cauda ao vivo NAO dispara refetch de historico (a prova: append local, sem refetch)', async () => {
    const spy = vi.spyOn(api.historyApi, 'getHistory')
    render(wrap(<SensorDetailPage code="TEMP-EXP-01" />))
    await waitFor(() => expect(spy).toHaveBeenCalledWith('TEMP-EXP-01', '24h'))
    const before = spy.mock.calls.length
    // liveApi emite ~1 ponto/s; deixa varios ticks ao vivo acontecerem.
    await new Promise((r) => setTimeout(r, 3500))
    // Nenhum tick ao vivo pode ter refetchado o historico — a cauda e anexada
    // localmente. getHistory continua com a mesma contagem.
    expect(spy.mock.calls.length).toBe(before)
    spy.mockRestore()
  })
})
