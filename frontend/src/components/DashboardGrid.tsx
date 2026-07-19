import { Responsive, WidthProvider, type Layout, type Layouts } from 'react-grid-layout'
import type { DashboardLayout } from '../lib/layout/schema'
import { WidgetFrame } from './WidgetFrame'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'

const ResponsiveGridLayout = WidthProvider(Responsive)

export function DashboardGrid({ layout, editing, onLayoutChange, onConfigure, onRemove }: {
  layout: DashboardLayout
  editing: boolean
  onLayoutChange?: (l: DashboardLayout) => void
  onConfigure?: (id: string) => void
  onRemove?: (id: string) => void
}) {
  const rglLayout: Layout[] = layout.widgets.map((w) => ({
    i: w.id,
    x: w.layout.x,
    y: w.layout.y,
    w: w.layout.w,
    h: w.layout.h,
    minW: w.layout.minW,
    minH: w.layout.minH,
  }))

  // Mobile: 1 coluna, ordenado por (y,x). Deriva empilhando os widgets na
  // ordem (y,x) e atribuindo linhas sequenciais.
  const mobileLayout: Layout[] = [...layout.widgets]
    .sort((a, b) => a.layout.y - b.layout.y || a.layout.x - b.layout.x)
    .map((w, i) => ({ i: w.id, x: 0, y: i, w: 1, h: w.layout.h }))

  // react-grid-layout chama onLayoutChange(currentLayout, allLayouts) tanto ao
  // arrastar/redimensionar quanto ao montar ou trocar de breakpoint. Se
  // mapeassemos de `current` (o layout do breakpoint ativo), uma janela
  // estreitada durante a edicao em desktop cruzaria para `xxs` e gravaria o
  // layout mobile de 1 coluna (x:0, w:1) por cima do `lg` salvo. Por isso
  // sempre mapeamos de volta a partir de `allLayouts.lg`, nunca do breakpoint
  // corrente.
  function handleChange(_current: Layout[], allLayouts: Layouts) {
    if (!editing || !onLayoutChange) return
    const lgLayout = allLayouts.lg
    if (!lgLayout) return
    const byId = Object.fromEntries(lgLayout.map((l) => [l.i, l]))
    onLayoutChange({
      ...layout,
      widgets: layout.widgets.map((w) => {
        const l = byId[w.id]
        return l ? { ...w, layout: { ...w.layout, x: l.x, y: l.y, w: l.w, h: l.h } } : w
      }),
    })
  }

  return (
    <ResponsiveGridLayout
      className="layout"
      layouts={{ lg: rglLayout, xxs: mobileLayout }}
      breakpoints={{ lg: 768, xxs: 0 }}
      cols={{ lg: layout.grid.cols, xxs: 1 }}
      rowHeight={layout.grid.rowHeight}
      margin={layout.grid.margin}
      isDraggable={editing}
      isResizable={editing}
      onLayoutChange={handleChange}
      draggableCancel="button"
    >
      {layout.widgets.map((w) => (
        <div key={w.id}>
          <WidgetFrame
            widget={w}
            editing={editing}
            onConfigure={onConfigure ? () => onConfigure(w.id) : undefined}
            onRemove={onRemove ? () => onRemove(w.id) : undefined}
          />
        </div>
      ))}
    </ResponsiveGridLayout>
  )
}
