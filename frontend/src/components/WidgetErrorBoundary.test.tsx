import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { WidgetErrorBoundary } from './WidgetErrorBoundary'

// Filho controlavel por variavel de modulo: permite simular "widget que
// lanca no render" e depois "widget que parou de lancar" sem trocar de
// componente -- o boundary so remonta os filhos reais ao resetar o estado.
let shouldThrow = true
function Flaky() {
  if (shouldThrow) throw new Error('boom')
  return <div>widget ok</div>
}

describe('WidgetErrorBoundary', () => {
  afterEach(() => {
    shouldThrow = true
  })

  it('renderiza os filhos normalmente quando nao ha erro', () => {
    render(
      <WidgetErrorBoundary widgetId="w1" widgetType="kpi" label="KPI (valor único)">
        <div>conteudo normal</div>
      </WidgetErrorBoundary>,
    )
    expect(screen.getByText('conteudo normal')).toBeInTheDocument()
  })

  it('mostra fallback com o rotulo do widget quando o filho lanca no render', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <WidgetErrorBoundary widgetId="w1" widgetType="kpi" label="KPI (valor único)">
        <Flaky />
      </WidgetErrorBoundary>,
    )
    expect(screen.getByText('Widget indisponível')).toBeInTheDocument()
    expect(screen.getByText('KPI (valor único)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Recarregar widget' })).toBeInTheDocument()
    spy.mockRestore()
  })

  it('"Recarregar widget" reseta o erro e remonta o filho', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <WidgetErrorBoundary widgetId="w1" widgetType="kpi" label="KPI (valor único)">
        <Flaky />
      </WidgetErrorBoundary>,
    )
    expect(screen.getByText('Widget indisponível')).toBeInTheDocument()

    shouldThrow = false
    await userEvent.click(screen.getByRole('button', { name: 'Recarregar widget' }))

    expect(screen.getByText('widget ok')).toBeInTheDocument()
    expect(screen.queryByText('Widget indisponível')).toBeNull()
    spy.mockRestore()
  })

  it('componentDidCatch loga widgetId, widgetType e componentStack via console.error', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <WidgetErrorBoundary widgetId="w42" widgetType="area" label="Card de área">
        <Flaky />
      </WidgetErrorBoundary>,
    )
    const call = spy.mock.calls.find((args) =>
      args.some((a) => JSON.stringify(a).includes('w42') && JSON.stringify(a).includes('area')),
    )
    expect(call).toBeDefined()
    const [, meta] = call!
    expect(JSON.stringify(meta)).toContain('componentStack')
    spy.mockRestore()
  })
})
