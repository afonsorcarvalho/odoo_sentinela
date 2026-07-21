import { describe, it, expect, vi } from 'vitest'
import { useEffect, type ReactNode } from 'react'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DashboardGrid } from './DashboardGrid'
import type { DashboardLayout } from '../lib/layout/schema'

// jsdom nao calcula largura real de container, entao o WidthProvider do
// react-grid-layout nunca mede >0px e o RGL real nao dispara onLayoutChange
// com dados uteis (ver task-12-report.md, RISK 2). Para testar
// especificamente a regressao do finding ("handleChange deve mapear sempre
// de allLayouts.lg, nunca do breakpoint ativo"), mockamos o modulo e
// simulamos o cenario exato do bug: RGL chama onLayoutChange com o layout
// mobile (xxs, x:0/w:1) como `current` porque a janela cruzou o breakpoint
// durante a edicao, mas `allLayouts.lg` ainda contem as posicoes desktop.
vi.mock('react-grid-layout', () => ({
  WidthProvider: (Comp: unknown) => Comp,
  Responsive: (props: {
    layouts: { lg: { i: string; x: number; y: number; w: number; h: number }[]; xxs: { i: string; x: number; y: number; w: number; h: number }[] }
    onLayoutChange?: (current: unknown, all: unknown) => void
    children: ReactNode
  }) => {
    useEffect(() => {
      // Simula o cruzamento de breakpoint: `current` e o layout mobile,
      // mas allLayouts.lg (desktop) esta presente.
      props.onLayoutChange?.(props.layouts.xxs, props.layouts)
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])
    return <div>{props.children}</div>
  },
}))

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

  it('mostra a grade de fundo apenas no modo edicao', () => {
    const { rerender } = renderWithClient(<DashboardGrid layout={layout} editing={false} />)
    expect(screen.queryByTestId('edit-grid-overlay')).toBeNull()

    rerender(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <DashboardGrid layout={layout} editing={true} />
      </QueryClientProvider>,
    )
    const overlay = screen.getByTestId('edit-grid-overlay')
    // Nao deve capturar o mouse, senao bloquearia drag/resize dos widgets.
    expect(overlay.className).toContain('pointer-events-none')
  })

  it('overlay de edicao tem classe de fade', () => {
    renderWithClient(<DashboardGrid layout={layout} editing={true} />)
    const overlay = screen.getByTestId('edit-grid-overlay')
    expect(overlay.className).toMatch(/edit-grid-fade/)
  })

  it('cada widget recebe a classe de entrada animada', () => {
    renderWithClient(<DashboardGrid layout={layout} editing={false} />)
    const frames = screen.getAllByTestId('widget-frame')
    // O wrapper de grid de cada widget carrega a classe de animação de entrada.
    frames.forEach((f) => {
      const wrapper = f.parentElement as HTMLElement
      expect(wrapper.className).toMatch(/animate-widget-in|widget-enter/)
    })
  })

  it('handleChange mapeia de allLayouts.lg, nao do breakpoint ativo (regressao)', () => {
    // Reproduz o finding: RGL dispara onLayoutChange(current=xxs, allLayouts)
    // ao cruzar breakpoint durante a edicao. O callback exposto pelo
    // DashboardGrid deve preservar as posicoes desktop (lg), nunca gravar o
    // layout mobile de 1 coluna (x:0, w:1) por cima delas.
    const onLayoutChange = vi.fn()
    renderWithClient(
      <DashboardGrid layout={layout} editing={true} onLayoutChange={onLayoutChange} />,
    )

    expect(onLayoutChange).toHaveBeenCalledTimes(1)
    const result: DashboardLayout = onLayoutChange.mock.calls[0][0]
    const k1 = result.widgets.find((w) => w.id === 'k1')
    const a1 = result.widgets.find((w) => w.id === 'a1')
    // Posicoes originais do layout `lg` (ver `layout` acima), nao x:0/w:1.
    expect(k1?.layout).toMatchObject({ x: 0, y: 0, w: 2, h: 2 })
    expect(a1?.layout).toMatchObject({ x: 2, y: 0, w: 3, h: 4 })
  })
})
