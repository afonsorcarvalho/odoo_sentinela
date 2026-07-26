import { useFloating, useDismiss, useInteractions, FloatingFocusManager, FloatingPortal, FloatingOverlay } from '@floating-ui/react'
import { WidgetConfigPopover } from './WidgetConfigPopover'
import { WIDGET_REGISTRY } from '../lib/widgets/registry'
import type { WidgetInstance } from '../lib/layout/schema'

// Drawer lateral de configuração do widget no modo edição. Mesmo shell do
// SensorDetailDrawer (FloatingOverlay ancestral do floating + FloatingFocusManager
// modal + drawer-panel + Esc/backdrop/✕ fecham) para que "configurar um widget"
// no editor abra na aba lateral direita, exatamente como o detalhe do sensor
// abre no modo normal. O corpo é o WidgetConfigPopover, reaproveitado sem
// alteração (form puro: widget + onChange).
//
// selectedId e o setter moram no DashboardEditor -- aqui só recebemos o widget
// atual + callbacks. Toda edição flui por onChange (updateWidget do editor, que
// muta o draft local); nada é escrito no servidor até o "Salvar".
export function WidgetConfigDrawer({
  widget,
  onChange,
  onClose,
}: {
  widget: WidgetInstance
  onChange: (w: WidgetInstance) => void
  onClose: () => void
}) {
  // Sem elemento de referência (o gatilho ⚙ vive no WidgetFrame, outro
  // componente). Focus trap + Esc + backdrop funcionam sem reference. Mesma
  // observação do SensorDetailDrawer.
  const { context, refs } = useFloating({
    open: true,
    onOpenChange: (open) => {
      if (!open) onClose()
    },
  })
  // outsidePress fecha ao clicar no backdrop; o FloatingOverlay precisa ser
  // ANCESTRAL do floating (não irmão) por causa do inert/markOthers do
  // FloatingFocusManager modal -- ver comentário longo no SensorDetailDrawer.
  const dismiss = useDismiss(context, { outsidePress: true, escapeKey: true })
  const { getFloatingProps } = useInteractions([dismiss])

  const label = WIDGET_REGISTRY[widget.type]?.label ?? widget.type

  return (
    <FloatingPortal>
      <FloatingOverlay
        data-testid="widget-config-drawer-backdrop"
        lockScroll
        className="z-40 drawer-backdrop"
        style={{ background: 'rgb(0 0 0 / 0.5)' }}
      >
        <FloatingFocusManager context={context}>
          <div
            ref={refs.setFloating}
            role="dialog"
            aria-modal="true"
            aria-label={`Configurar widget ${label}`}
            className="drawer-panel z-50 flex flex-col motion-reduce:animate-none"
            style={{ background: 'var(--color-surface)', boxShadow: 'var(--shadow-menu)' }}
            {...getFloatingProps()}
          >
            <div className="flex justify-end p-2">
              <button
                type="button"
                onClick={onClose}
                aria-label="Fechar"
                className="min-h-11 min-w-11 rounded-md text-lg font-semibold outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
                style={{ color: 'var(--color-muted)' }}
              >
                ✕
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
              <WidgetConfigPopover widget={widget} onChange={onChange} onClose={onClose} />
            </div>
          </div>
        </FloatingFocusManager>
      </FloatingOverlay>
    </FloatingPortal>
  )
}
