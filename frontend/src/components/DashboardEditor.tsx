import { useState } from 'react'
import { DashboardGrid } from './DashboardGrid'
import { WidgetPalette } from './WidgetPalette'
import { newWidget } from '../lib/widgets/newWidget'
import { useSaveLayout } from '../lib/queries'
import type { DashboardLayout, WidgetInstance, WidgetType } from '../lib/layout/schema'

export function DashboardEditor({ layout, onExit }: { layout: DashboardLayout; onExit: () => void }) {
  const [draft, setDraft] = useState<DashboardLayout>(layout)
  const [droppingType, setDroppingType] = useState<WidgetType | null>(null)
  const save = useSaveLayout()

  function addWidget(type: WidgetType) {
    setDraft((d) => ({ ...d, widgets: [...d.widgets, newWidget(type, d.widgets)] }))
  }
  function dropWidget(pos: { x: number; y: number }) {
    if (!droppingType) return
    setDraft((d) => ({ ...d, widgets: [...d.widgets, newWidget(droppingType, d.widgets, pos)] }))
    setDroppingType(null)
  }
  function removeWidget(id: string) {
    setDraft((d) => ({ ...d, widgets: d.widgets.filter((w) => w.id !== id) }))
  }
  function updateWidget(w: WidgetInstance) {
    setDraft((d) => ({ ...d, widgets: d.widgets.map((x) => (x.id === w.id ? w : x)) }))
  }

  return (
    <div>
      <div className="mb-3 flex items-center gap-3">
        <WidgetPalette onAdd={addWidget} onDragStartType={setDroppingType} onDragEnd={() => setDroppingType(null)} />
        <div className="ml-auto flex gap-2">
          <button
            type="button"
            onClick={() => save.mutate(draft, { onSuccess: onExit })}
            disabled={save.isPending}
            className="rounded px-3 py-1 text-sm font-bold text-white"
            style={{ background: 'var(--color-primary)' }}
          >
            Salvar
          </button>
          <button type="button" onClick={onExit} className="rounded border px-3 py-1 text-sm">Cancelar</button>
        </div>
      </div>

      <DashboardGrid
        layout={draft}
        editing
        onLayoutChange={setDraft}
        onWidgetChange={updateWidget}
        onRemove={removeWidget}
        droppingType={droppingType}
        onDropWidget={dropWidget}
      />
    </div>
  )
}
