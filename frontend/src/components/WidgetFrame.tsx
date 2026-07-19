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
    <div data-testid="widget-frame" className="relative h-full w-full overflow-hidden">
      {editing && (
        <div className="absolute right-1 top-1 z-10 flex gap-1">
          <button type="button" onClick={onConfigure} aria-label="Configurar widget"
                  className="rounded bg-black/40 px-1.5 text-xs text-white">⚙</button>
          <button type="button" onClick={onRemove} aria-label="Remover widget"
                  className="rounded bg-black/40 px-1.5 text-xs text-white">✕</button>
        </div>
      )}
      {descriptor.render(widget)}
    </div>
  )
}
