import type { WidgetInstance } from '../lib/layout/schema'
import { WIDGET_REGISTRY } from '../lib/widgets/registry'

export function WidgetFrame({ widget, editing, onConfigure, onRemove }: {
  widget: WidgetInstance
  editing: boolean
  onConfigure?: () => void
  onRemove?: () => void
}) {
  const descriptor = WIDGET_REGISTRY[widget.type]
  return (
    <div data-testid="widget-frame" className="@container relative flex h-full w-full flex-col overflow-hidden">
      {editing && (
        <div className="absolute right-1 top-1 z-10 flex gap-1">
          <button type="button" onClick={onConfigure} aria-label="Configurar widget"
                  className="rounded bg-black/40 px-1.5 text-xs text-white">⚙</button>
          <button type="button" onClick={onRemove} aria-label="Remover widget"
                  className="rounded bg-black/40 px-1.5 text-xs text-white">✕</button>
        </div>
      )}
      {/* wrapper min-h-0/flex-1: garante que o conteudo herda a altura do
          frame mesmo dentro de um container flex (senão o filho cresce livre) */}
      <div className="min-h-0 flex-1">{descriptor.render(widget)}</div>
    </div>
  )
}
