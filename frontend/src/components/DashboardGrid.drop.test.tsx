import { describe, it, expect, vi } from 'vitest'
import type { ReactNode } from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DashboardGrid } from './DashboardGrid'
import type { DashboardLayout } from '../lib/layout/schema'

// Arquivo dedicado (mock proprio, isolado do DashboardGrid.test.tsx) para
// testar o fio onDrop -> onDropWidget sem herdar o comportamento de
// onLayoutChange-no-mount do outro mock. O RGL real dispara onDrop(layout,
// item, event) no drop nativo; aqui simulamos via um botao que so o teste
// aciona (opt-in), evitando disparo acidental noutros testes do suite.
vi.mock('react-grid-layout', () => ({
  WidthProvider: (Comp: unknown) => Comp,
  Responsive: (props: {
    onDrop?: (layout: unknown[], item: { i: string; x: number; y: number; w: number; h: number }) => void
    children: ReactNode
  }) => (
    <div>
      <button
        type="button"
        data-testid="fake-rgl-drop"
        onClick={() => props.onDrop?.([], { i: '__dropping__', x: 3, y: 5, w: 2, h: 2 })}
      >
        simular drop
      </button>
      {props.children}
    </div>
  ),
}))

const layout: DashboardLayout = {
  version: 1,
  grid: { cols: 12, rowHeight: 40, margin: [8, 8] },
  widgets: [],
}

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('DashboardGrid onDrop', () => {
  it('chama onDropWidget com a posição (x,y) do item solto', () => {
    const onDropWidget = vi.fn()
    renderWithClient(
      <DashboardGrid
        layout={layout}
        editing
        droppingType="kpi"
        onDropWidget={onDropWidget}
      />,
    )
    fireEvent.click(screen.getByTestId('fake-rgl-drop'))
    expect(onDropWidget).toHaveBeenCalledWith({ x: 3, y: 5 })
  })
})
