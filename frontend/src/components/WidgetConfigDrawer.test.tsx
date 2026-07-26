import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { WidgetConfigDrawer } from './WidgetConfigDrawer'
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

describe('WidgetConfigDrawer', () => {
  it('renderiza o form de config do widget dentro do drawer (role=dialog)', () => {
    wrap(<WidgetConfigDrawer widget={w} onChange={vi.fn()} onClose={vi.fn()} />)
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    // WidgetConfigPopover mostra o label do tipo no header
    expect(screen.getByText('KPI (valor único)')).toBeInTheDocument()
  })

  it('fecha ao pressionar Escape', async () => {
    const onClose = vi.fn()
    wrap(<WidgetConfigDrawer widget={w} onChange={vi.fn()} onClose={onClose} />)
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('fecha ao clicar no backdrop', async () => {
    const onClose = vi.fn()
    wrap(<WidgetConfigDrawer widget={w} onChange={vi.fn()} onClose={onClose} />)
    await userEvent.click(screen.getByTestId('widget-config-drawer-backdrop'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('fecha ao clicar no ✕', async () => {
    const onClose = vi.fn()
    wrap(<WidgetConfigDrawer widget={w} onChange={vi.fn()} onClose={onClose} />)
    await userEvent.click(screen.getByLabelText('Fechar'))
    expect(onClose).toHaveBeenCalled()
  })

  it('propaga edição via onChange (editar o rótulo do KPI)', async () => {
    const onChange = vi.fn()
    wrap(<WidgetConfigDrawer widget={w} onChange={onChange} onClose={vi.fn()} />)
    // fireEvent.change em vez de userEvent.type: o focus-trap modal do
    // FloatingFocusManager rouba o foco de volta e engole os keystrokes do
    // userEvent no jsdom; o que importa aqui e a propagacao via onChange.
    fireEvent.change(screen.getByLabelText('Rótulo'), { target: { value: 'X' } })
    expect(onChange).toHaveBeenCalled()
    const arg = onChange.mock.calls.at(-1)![0] as WidgetInstance
    expect(arg.options?.label).toBe('X')
  })
})
