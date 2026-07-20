import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TimeseriesWidget } from './TimeseriesWidget'

vi.mock('../../lib/queries', () => ({
  useSensors: () => ({ data: [{ sensor_code: 'S1', name: 'Sensor Um', area: { area_code: 'A', name: 'Área' } }] }),
  useHistory: vi.fn(() => ({ data: undefined })),
  useThreshold: () => ({ data: null }),
}))
vi.mock('../../lib/useLiveTail', () => ({ useLiveTail: () => ({ tail: [] }) }))
vi.mock('../TimeSeriesChart', () => ({ TimeSeriesChart: () => <div data-testid="chart" /> }))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('TimeseriesWidget', () => {
  it('mostra titulo do sensor e o seletor de janela', () => {
    wrap(<TimeseriesWidget sensorCode="S1" />)
    expect(screen.getByText('Sensor Um')).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Janela temporal' })).toBeInTheDocument()
  })

  it('troca a janela ao clicar num chip', async () => {
    const { useHistory } = await import('../../lib/queries')
    wrap(<TimeseriesWidget sensorCode="S1" defaultWindow="24h" />)
    await userEvent.click(screen.getByRole('button', { name: '7d' }))
    expect(useHistory).toHaveBeenLastCalledWith('S1', '7d')
  })
})
