import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { WidgetFrame } from './WidgetFrame'
import type { WidgetInstance } from '../lib/layout/schema'

vi.mock('../lib/queries', () => ({
  useSensors: () => ({ data: [] }),
  useThreshold: () => ({ data: undefined }),
}))

const w: WidgetInstance = { id: 'k1', type: 'kpi', layout: { x: 0, y: 0, w: 2, h: 2 }, binding: {}, options: {} }

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('WidgetFrame edição', () => {
  it('clicar em configurar dispara onConfigure (config abre na aba lateral, não inline)', async () => {
    const onConfigure = vi.fn()
    wrap(<WidgetFrame widget={w} editing onConfigure={onConfigure} onRemove={vi.fn()} />)
    await userEvent.click(screen.getByLabelText('Configurar widget'))
    expect(onConfigure).toHaveBeenCalledTimes(1)
    // O form de config NÃO é renderizado pelo frame (mora no drawer do editor).
    expect(screen.queryByText('KPI (valor único)')).toBeNull()
  })

  it('realça a tile quando selected', () => {
    const { rerender } = wrap(<WidgetFrame widget={w} editing selected={false} onConfigure={vi.fn()} onRemove={vi.fn()} />)
    expect(screen.getByTestId('widget-frame').className).not.toMatch(/ring-2/)
    rerender(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <WidgetFrame widget={w} editing selected onConfigure={vi.fn()} onRemove={vi.fn()} />
      </QueryClientProvider>,
    )
    expect(screen.getByTestId('widget-frame').className).toMatch(/ring-2/)
  })

  it('em modo leitura não mostra o botão configurar', () => {
    wrap(<WidgetFrame widget={w} editing={false} />)
    expect(screen.queryByLabelText('Configurar widget')).toBeNull()
  })
})
