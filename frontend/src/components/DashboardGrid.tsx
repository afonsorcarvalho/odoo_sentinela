import { Responsive, WidthProvider, type Layout } from 'react-grid-layout'
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

  function handleChange(current: Layout[]) {
    if (!editing || !onLayoutChange) return
    const byId = Object.fromEntries(current.map((l) => [l.i, l]))
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
