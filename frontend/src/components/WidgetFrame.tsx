import { useState } from 'react'
import { useFloating, offset, flip, shift, autoUpdate, FloatingPortal, useDismiss, useInteractions } from '@floating-ui/react'
import type { WidgetInstance } from '../lib/layout/schema'
import { WIDGET_REGISTRY } from '../lib/widgets/registry'
import { WidgetConfigPopover } from './WidgetConfigPopover'

export function WidgetFrame({ widget, editing, onChange, onRemove }: {
  widget: WidgetInstance
  editing: boolean
  onChange?: (w: WidgetInstance) => void
  onRemove?: () => void
}) {
  const descriptor = WIDGET_REGISTRY[widget.type]
  const [open, setOpen] = useState(false)
  const { refs, floatingStyles, context } = useFloating({
    open,
    onOpenChange: setOpen,
    placement: 'bottom-end',
    middleware: [offset(6), flip(), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
  })

  const dismiss = useDismiss(context)
  const { getReferenceProps, getFloatingProps } = useInteractions([dismiss])

  return (
    <div data-testid="widget-frame" className="@container relative flex h-full w-full flex-col overflow-hidden">
      {editing && (
        <div className="absolute right-1 top-1 z-10 flex gap-1">
          <button ref={refs.setReference} type="button" onClick={() => setOpen((o) => !o)}
                  aria-label="Configurar widget" aria-haspopup="dialog" aria-expanded={open}
                  className="rounded bg-black/40 px-1.5 text-xs text-white" {...getReferenceProps()}>⚙</button>
          <button type="button" onClick={onRemove} aria-label="Remover widget"
                  className="rounded bg-black/40 px-1.5 text-xs text-white">✕</button>
        </div>
      )}
      {/* wrapper min-h-0/flex-1: garante que o conteudo herda a altura do
          frame mesmo dentro de um container flex (senão o filho cresce livre) */}
      <div className="min-h-0 flex-1">{descriptor.render(widget)}</div>
      {editing && open && onChange && (
        <FloatingPortal>
          <div ref={refs.setFloating} style={floatingStyles} className="z-50 w-60"
               role="dialog" aria-label="Configuração do widget" {...getFloatingProps()}>
            <WidgetConfigPopover widget={widget} onChange={onChange} onClose={() => setOpen(false)} />
          </div>
        </FloatingPortal>
      )}
    </div>
  )
}
