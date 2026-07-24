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
const mockTail = vi.fn(() => ({ tail: [], last: null as unknown }))
vi.mock('../../lib/useLiveTail', () => ({ useLiveTail: () => mockTail() }))
vi.mock('../../lib/useNow', () => ({ useNow: () => 1_000_000 }))
vi.mock('../TimeSeriesChart', () => ({ TimeSeriesChart: () => <div data-testid="chart" /> }))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('TimeseriesWidget', () => {
  it('mostra titulo do sensor e o seletor de janela', () => {
    mockTail.mockReturnValue({ tail: [], last: { value: 1, alarm_state: 'ok', ts: 1_000_000 } })
    wrap(<TimeseriesWidget sensorCode="S1" />)
    expect(screen.getByText('Sensor Um')).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Janela temporal' })).toBeInTheDocument()
  })

  it('troca a janela ao clicar num chip', async () => {
    mockTail.mockReturnValue({ tail: [], last: { value: 1, alarm_state: 'ok', ts: 1_000_000 } })
    const { useHistory } = await import('../../lib/queries')
    wrap(<TimeseriesWidget sensorCode="S1" defaultWindow="24h" />)
    await userEvent.click(screen.getByRole('button', { name: '7d' }))
    expect(useHistory).toHaveBeenLastCalledWith('S1', '7d')
  })

  it('mostra badge de frescor quando o ultimo dado esta offline', () => {
    mockTail.mockReturnValue({ tail: [], last: { value: 10, alarm_state: 'ok', ts: 1_000_000 - 20 * 60_000 } })
    wrap(<TimeseriesWidget sensorCode="S1" />)
    expect(screen.getByTestId('freshness-badge')).toBeInTheDocument()
  })

  it('sensor fresh: sem badge', () => {
    mockTail.mockReturnValue({ tail: [], last: { value: 10, alarm_state: 'ok', ts: 1_000_000 } })
    wrap(<TimeseriesWidget sensorCode="S1" />)
    expect(screen.queryByTestId('freshness-badge')).not.toBeInTheDocument()
  })
})
