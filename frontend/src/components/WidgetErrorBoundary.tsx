import { Component, type ReactNode } from 'react'

// Boundary por widget: um bug de render num widget individual (acesso a
// dado indefinido, tipo inesperado, erro numa lib de grafico) nao pode
// derrubar o dashboard inteiro. Componente de classe proprio (nao a lib
// react-error-boundary) -- React 19 ainda nao tem API de boundary em hook
// (exige componentDidCatch/getDerivedStateFromError), e o requisito e
// simples o bastante (capturar, mostrar fallback, resetar) para nao
// justificar uma dependencia nova. Ver docs/superpowers/specs/2026-07-19-widget-error-boundary-design.md
//
// Nao captura falha de dado (react-query isError): isso e estado, exposto
// pelo hook, nao excecao lancada durante o render -- continua tratado
// dentro de cada widget (padrao WidgetPlaceholder/loading/erro).
type Props = {
  widgetId: string
  widgetType: string
  label: string
  children: ReactNode
}

type State = {
  error: Error | null
}

export class WidgetErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: { componentStack: string }) {
    // Sem telemetria remota nesta fase (fora de escopo) -- so console.error.
    console.error('[WidgetErrorBoundary] widget quebrou durante o render', {
      widgetId: this.props.widgetId,
      widgetType: this.props.widgetType,
      error,
      componentStack: info.componentStack,
    })
  }

  reset = () => {
    this.setState({ error: null })
  }

  render() {
    if (this.state.error) {
      return (
        <div
          className="flex h-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-3 text-center text-xs"
          style={{ color: 'var(--color-crit)', borderColor: 'var(--color-crit)' }}
        >
          <p>Widget indisponível</p>
          <p className="font-semibold">{this.props.label}</p>
          <button
            type="button"
            onClick={this.reset}
            className="rounded border px-2 py-1 text-xs"
            style={{ borderColor: 'var(--color-crit)', color: 'var(--color-crit)' }}
          >
            Recarregar widget
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
