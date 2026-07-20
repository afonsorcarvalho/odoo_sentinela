import { useState } from 'react'
import { useFloating, offset, flip, shift, autoUpdate, FloatingPortal, useDismiss, useInteractions } from '@floating-ui/react'
import type { WidgetInstance } from '../lib/layout/schema'
import { WIDGET_REGISTRY } from '../lib/widgets/registry'
import { WidgetConfigPopover } from './WidgetConfigPopover'
import { WidgetErrorBoundary } from './WidgetErrorBoundary'
import { WidgetPlaceholder } from './widgets/WidgetPlaceholder'

export function WidgetFrame({ widget, editing, onChange, onRemove }: {
  widget: WidgetInstance
  editing: boolean
  onChange?: (w: WidgetInstance) => void
  onRemove?: () => void
}) {
  // widget.type pode ser um tipo que nao existe mais no registry (layout
  // salvo antes de o tipo ser removido) -- descriptor fica undefined.
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
