import { useMemo, useState } from 'react'
import { useFloating, useDismiss, useInteractions, FloatingFocusManager, FloatingPortal, FloatingOverlay } from '@floating-ui/react'
import type { EntityConfig } from './types'

// Modal-tabela "Pesquisar mais" (Odoo-like). Genérica: só sabe de EntityConfig.
// Abre SOBRE o contexto atual (inclusive sobre o WidgetConfigDrawer) — shell
// igual ao SensorDetailDrawer: FloatingOverlay ancestral + FocusManager modal.
// Fechar (Esc/backdrop/✕/Cancelar) chama onClose e NÃO afeta o drawer por baixo.
export function SearchMoreDialog<T>({
  items, config, multiple, initialSelectedIds, onConfirm, onClose, title,
}: {
  items: T[]
  config: EntityConfig<T>
  multiple: boolean
  initialSelectedIds: string[]
  onConfirm: (ids: string[]) => void
  onClose: () => void
  title?: string
}) {
  const [query, setQuery] = useState('')
  const [marked, setMarked] = useState<string[]>(initialSelectedIds)

  const { context, refs } = useFloating({ open: true, onOpenChange: (o) => { if (!o) onClose() } })
  const dismiss = useDismiss(context, { outsidePress: true, escapeKey: true })
  const { getFloatingProps } = useInteractions([dismiss])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return items
    return items.filter((it) => config.searchText(it).toLowerCase().includes(q))
  }, [items, config, query])

  function toggle(id: string) {
    setMarked((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]))
  }

  return (
    <FloatingPortal>
      <FloatingOverlay lockScroll className="z-[60] drawer-backdrop" style={{ background: 'rgb(0 0 0 / 0.5)' }} data-testid="search-more-backdrop">
        <FloatingFocusManager context={context}>
          <div
            ref={refs.setFloating}
            role="dialog"
            aria-modal="true"
            aria-label={title ?? 'Pesquisar'}
            className="fixed left-1/2 top-1/2 z-[61] flex max-h-[80vh] w-[min(720px,94vw)] -translate-x-1/2 -translate-y-1/2 flex-col rounded-lg"
            style={{ background: 'var(--color-surface)', boxShadow: 'var(--shadow-menu)' }}
            {...getFloatingProps()}
          >
            <div className="flex items-center gap-2 p-3">
              <input
                aria-label="Buscar"
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Buscar em todos os campos…"
                className="w-full rounded border px-2 py-1 text-sm"
                style={{ borderColor: 'var(--color-muted)' }}
              />
              <button type="button" aria-label="Fechar" onClick={onClose} className="min-h-9 min-w-9 rounded text-lg" style={{ color: 'var(--color-muted)' }}>✕</button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto px-3">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr>
                    {multiple && <th className="w-8" />}
                    {config.columns.map((c) => <th key={c.header} scope="col" className="px-2 py-1 font-semibold" style={{ color: 'var(--color-muted)' }}>{c.header}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 && (
                    <tr><td colSpan={config.columns.length + (multiple ? 1 : 0)} className="px-2 py-3 text-center" style={{ color: 'var(--color-muted)' }}>Nada encontrado</td></tr>
                  )}
                  {filtered.map((it) => {
                    const id = config.getId(it)
                    return (
                      <tr
                        key={id}
                        className="cursor-pointer hover:bg-black/10"
                        onClick={multiple ? undefined : () => { onConfirm([id]); onClose() }}
                      >
                        {multiple && (
                          <td className="px-2 py-1">
                            <input
                              type="checkbox"
                              aria-label={config.getLabel(it)}
                              checked={marked.includes(id)}
                              onChange={() => toggle(id)}
                            />
                          </td>
                        )}
                        {config.columns.map((c, i) => <td key={i} className="px-2 py-1">{c.cell(it)}</td>)}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {multiple && (
              <div className="flex justify-end gap-2 p-3">
                <button type="button" onClick={onClose} className="rounded border px-3 py-1 text-sm">Cancelar</button>
                <button type="button" onClick={() => { onConfirm(marked); onClose() }} className="rounded px-3 py-1 text-sm font-bold text-white" style={{ background: 'var(--color-primary)' }}>Confirmar</button>
              </div>
            )}
          </div>
        </FloatingFocusManager>
      </FloatingOverlay>
    </FloatingPortal>
  )
}
