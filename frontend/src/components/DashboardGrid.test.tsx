import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DashboardGrid } from './DashboardGrid'
import type { DashboardLayout } from '../lib/layout/schema'

const layout: DashboardLayout = {
  version: 1,
  grid: { cols: 12, rowHeight: 40, margin: [8, 8] },
  widgets: [
    { id: 'k1', type: 'kpi', layout: { x: 0, y: 0, w: 2, h: 2 }, binding: {}, options: {} },
    { id: 'a1', type: 'alarms', layout: { x: 2, y: 0, w: 3, h: 4 }, binding: {}, options: { scope: 'site' } },
  ],
}

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('DashboardGrid', () => {
  it('renderiza um frame por widget do layout', () => {
    renderWithClient(<DashboardGrid layout={layout} editing={false} />)
    // WidthProvider mede a largura do container (0 no jsdom), entao o proprio
    // .react-grid-item pode nao renderizar. Contamos os WidgetFrame por testid.
    expect(screen.getAllByTestId('widget-frame').length).toBe(2)
  })

  it('em modo leitura nao mostra o chrome de edicao', () => {
    renderWithClient(<DashboardGrid layout={layout} editing={false} />)
    expect(screen.queryAllByLabelText('Remover widget').length).toBe(0)
  })

  it('em modo edicao mostra botoes de configurar/remover por widget', () => {
    renderWithClient(<DashboardGrid layout={layout} editing={true} />)
    expect(screen.getAllByLabelText('Remover widget').length).toBe(2)
    expect(screen.getAllByLabelText('Configurar widget').length).toBe(2)
  })
})
