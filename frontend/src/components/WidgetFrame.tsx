import type { WidgetInstance } from '../lib/layout/schema'
import { WIDGET_REGISTRY } from '../lib/widgets/registry'
import { WidgetErrorBoundary } from './WidgetErrorBoundary'
import { WidgetPlaceholder } from './widgets/WidgetPlaceholder'

export function WidgetFrame({ widget, editing, selected, onConfigure, onRemove }: {
  widget: WidgetInstance
  editing: boolean
  // Widget atualmente selecionado para config (drawer aberto nele). Realça a
  // tile para o admin saber qual está editando na aba lateral.
  selected?: boolean
  // Abre a config deste widget na aba lateral (drawer no DashboardEditor). A
  // config em si NÃO mora mais aqui (era um popover flutuante) -- o frame só
  // reporta "quero configurar este widget"; o editor decide/renderiza o drawer.
  onConfigure?: () => void
  onRemove?: () => void
}) {
  // widget.type pode ser um tipo que nao existe mais no registry (layout
  // salvo antes de o tipo ser removido) -- descriptor fica undefined.
  const descriptor = WIDGET_REGISTRY[widget.type]

  if (!descriptor) {
    // Sem descriptor nao ha .render nem .label para usar -- so o chrome de
    // remover (⚙ nao faz sentido sem descriptor para configurar) e um
    // placeholder generico, para nao travar o dashboard com uma tile
    // irremovivel.
    return (
      <div data-testid="widget-frame" className="@container relative flex h-full w-full flex-col overflow-hidden">
        {editing && (
          <div className="absolute right-1 top-1 z-10 flex gap-1">
            <button type="button" onClick={onRemove} aria-label="Remover widget"
                    className="rounded bg-black/40 px-1.5 text-xs text-white">✕</button>
          </div>
        )}
        <div className="min-h-0 flex-1">
          <WidgetPlaceholder texto="Tipo de widget desconhecido" />
        </div>
      </div>
    )
  }

  return (
    <div
      data-testid="widget-frame"
      className={`@container relative flex h-full w-full flex-col overflow-hidden${selected ? ' ring-2 ring-[var(--color-primary)] rounded' : ''}`}
    >
      {editing && (
        <div className="absolute right-1 top-1 z-10 flex gap-1">
          <button type="button" onClick={onConfigure} aria-label="Configurar widget" aria-haspopup="dialog"
                  className="rounded bg-black/40 px-1.5 text-xs text-white">⚙</button>
          <button type="button" onClick={onRemove} aria-label="Remover widget"
                  className="rounded bg-black/40 px-1.5 text-xs text-white">✕</button>
        </div>
      )}
      {/* wrapper min-h-0/flex-1: garante que o conteudo herda a altura do
          frame mesmo dentro de um container flex (senão o filho cresce livre).
          O boundary envolve so o conteudo renderizado pelo widget -- os
          botoes ⚙/✕ acima ficam fora dele de proposito (spec A1): se o
          widget quebrado levasse junto o botao de remover, o admin ficaria
          preso com uma tile quebrada e irremovivel. key deriva de
          binding+options para remontar (limpando o erro) quando o admin
          reconfigura o widget que estava quebrado. */}
      <div className="min-h-0 flex-1">
        <WidgetErrorBoundary
          key={JSON.stringify({ binding: widget.binding, options: widget.options })}
          widgetId={widget.id}
          widgetType={widget.type}
          label={descriptor.label}
        >
          {descriptor.render(widget)}
        </WidgetErrorBoundary>
      </div>
    </div>
  )
}
