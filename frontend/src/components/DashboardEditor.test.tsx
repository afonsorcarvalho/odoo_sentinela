import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DashboardEditor } from './DashboardEditor'
import type { DashboardLayout } from '../lib/layout/schema'

const layout: DashboardLayout = {
  version: 1,
  grid: { cols: 12, rowHeight: 40, margin: [8, 8] },
  widgets: [{ id: 'k1', type: 'kpi', layout: { x: 0, y: 0, w: 2, h: 2 }, binding: {}, options: {} }],
}

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('DashboardEditor', () => {
  it('adiciona um widget pela palette', async () => {
    renderWithClient(<DashboardEditor layout={layout} onExit={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: /adicionar/i }))
    await userEvent.click(screen.getByRole('button', { name: /card de área/i }))
    // agora deve haver 2 botões de remover (1 original + 1 novo)
    expect(screen.getAllByLabelText('Remover widget').length).toBe(2)
  })
  it('cancelar chama onExit', async () => {
    const onExit = vi.fn()
    renderWithClient(<DashboardEditor layout={layout} onExit={onExit} />)
    await userEvent.click(screen.getByRole('button', { name: /cancelar/i }))
    expect(onExit).toHaveBeenCalled()
  })
})
