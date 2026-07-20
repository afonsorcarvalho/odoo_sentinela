import { describe, it, expect, vi, afterEach } from 'vitest'
import type { ReactNode } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { WidgetFrame } from './WidgetFrame'
import type { WidgetInstance } from '../lib/layout/schema'

// Alarms usa useAlarms + useSensors (via AlarmsWidget real, nao mockado
// individualmente) -- widget "vizinho saudavel" nos testes de isolamento.
vi.mock('../lib/queries', () => ({
  useSensors: () => ({ data: [] }),
  useAlarms: () => ({ data: [] }),
}))

// render() do tipo 'kpi' e substituido por uma funcao controlavel por teste,
// permitindo simular: crash no render, recuperacao apos reconfig, e estado
// de erro de dado (isError) que NAO deve acionar o boundary (nao lanca).
let kpiRender: (w: WidgetInstance) => ReactNode = () => <div>kpi default</div>
vi.mock('../lib/widgets/registry', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/widgets/registry')>()
  return {
    WIDGET_REGISTRY: {
      ...actual.WIDGET_REGISTRY,
      kpi: { ...actual.WIDGET_REGISTRY.kpi, render: (w: WidgetInstance) => kpiRender(w) },
    },
  }
})

function Boom(): never {
  throw new Error('kaboom')
}

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

const kpiWidget: WidgetInstance = { id: 'k1', type: 'kpi', layout: { x: 0, y: 0, w: 2, h: 2 }, binding: {}, options: {} }
const alarmsWidget: WidgetInstance = { id: 'a1', type: 'alarms', layout: { x: 2, y: 0, w: 3, h: 4 }, binding: {}, options: {} }

describe('WidgetFrame + WidgetErrorBoundary (integração)', () => {
  afterEach(() => {
    kpiRender = () => <div>kpi default</div>
  })

  it('headline: um widget lança no render, o vizinho continua renderizado e o fallback mostra o rótulo', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    kpiRender = () => <Boom />
    wrap(
      <>
        <WidgetFrame widget={kpiWidget} editing={false} />
        <WidgetFrame widget={alarmsWidget} editing={false} />
      </>,
    )
    // Widget quebrado mostra fallback com o rótulo do tipo.
    expect(screen.getByText('Widget indisponível')).toBeInTheDocument()
    expect(screen.getByText('KPI (valor único)')).toBeInTheDocument()
    // Vizinho (alarms) segue renderizado normalmente.
    expect(screen.getByText('Nenhum alarme ativo.')).toBeInTheDocument()
    spy.mockRestore()
  })

  it('reconfigurar binding/options limpa o erro (remonta via key, sem clicar em recarregar)', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    kpiRender = (w) => (w.binding.sensorCode ? <div>ok-{w.binding.sensorCode}</div> : <Boom />)
    const { rerender } = wrap(<WidgetFrame widget={kpiWidget} editing={false} />)
    expect(screen.getByText('Widget indisponível')).toBeInTheDocument()

    const reconfigured: WidgetInstance = { ...kpiWidget, binding: { sensorCode: 's1' } }
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    rerender(
      <QueryClientProvider client={qc}>
        <WidgetFrame widget={reconfigured} editing={false} />
      </QueryClientProvider>,
    )

    expect(screen.getByText('ok-s1')).toBeInTheDocument()
    expect(screen.queryByText('Widget indisponível')).toBeNull()
    spy.mockRestore()
  })

  it('falha de dado (react-query isError) não dispara o boundary — segue no estado in-widget', () => {
    // Nao exercita react-query de verdade -- so simula o contrato que ele
    // segue (isError e estado exposto pelo hook, nunca um throw durante o
    // render). A asserção que importa aqui e a do spy: prova que um render
    // que nao lança nunca aciona componentDidCatch, reforcando que o
    // boundary e so backstop pra crash de render, nao substituto dos
    // estados de loading/erro/vazio de cada widget.
    kpiRender = () => <div>Erro ao carregar dado (in-widget)</div>
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    wrap(<WidgetFrame widget={kpiWidget} editing={false} />)
    expect(screen.getByText('Erro ao carregar dado (in-widget)')).toBeInTheDocument()
    expect(screen.queryByText('Widget indisponível')).toBeNull()
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
  })

  it('remover um widget quebrado em modo edição funciona (botão ✕ fica fora do boundary)', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    kpiRender = () => <Boom />
    const onRemove = vi.fn()
    wrap(<WidgetFrame widget={kpiWidget} editing onChange={vi.fn()} onRemove={onRemove} />)
    expect(screen.getByText('Widget indisponível')).toBeInTheDocument()

    await userEvent.click(screen.getByLabelText('Remover widget'))
    expect(onRemove).toHaveBeenCalledTimes(1)
    spy.mockRestore()
  })

  it('tipo desconhecido no layout → WidgetPlaceholder, sem crash do WidgetFrame', () => {
    const unknownWidget = { ...kpiWidget, id: 'u1', type: 'nao-existe' } as unknown as WidgetInstance
    wrap(<WidgetFrame widget={unknownWidget} editing={false} />)
    expect(screen.getByTestId('widget-frame')).toBeInTheDocument()
    expect(screen.getByText('Tipo de widget desconhecido')).toBeInTheDocument()
  })
})
