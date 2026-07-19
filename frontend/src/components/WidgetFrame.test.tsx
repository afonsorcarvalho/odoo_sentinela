import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { WidgetFrame } from './WidgetFrame'
import type { WidgetInstance } from '../lib/layout/schema'

vi.mock('../lib/queries', () => ({ useSensors: () => ({ data: [] }) }))

const w: WidgetInstance = { id: 'k1', type: 'kpi', layout: { x: 0, y: 0, w: 2, h: 2 }, binding: {}, options: {} }

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('WidgetFrame edição', () => {
  it('abre o popover de config ao clicar no botão configurar', async () => {
    wrap(<WidgetFrame widget={w} editing onChange={vi.fn()} onRemove={vi.fn()} />)
    expect(screen.queryByText('KPI (valor único)')).toBeNull()
    await userEvent.click(screen.getByLabelText('Configurar widget'))
    // WidgetConfigPopover mostra o label do tipo no header
    expect(screen.getByText('KPI (valor único)')).toBeInTheDocument()
  })
})
