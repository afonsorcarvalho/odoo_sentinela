import { useEffect, useRef, useState } from 'react'
import { Responsive, WidthProvider, type Layout, type Layouts } from 'react-grid-layout'
import type { DashboardLayout, WidgetInstance, WidgetType } from '../lib/layout/schema'
import { WIDGET_REGISTRY } from '../lib/widgets/registry'
import { WidgetFrame } from './WidgetFrame'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'

const ResponsiveGridLayout = WidthProvider(Responsive)

// Grade de fundo do modo edicao: desenha as linhas de coluna/linha usando o
// mesmo passo do react-grid-layout, para dar ao admin a nocao de "onde os
// widgets encaixam". Passo de coluna = (largura - margem) / cols (deduzido de
// left_i = margem + i*(colWidth+margem), cuja periodicidade e (W-margem)/cols).
// Linhas sao px fixo (rowHeight + margem). pointer-events-none para nao roubar
// o mouse do drag/resize.
function EditGridOverlay({ grid, width }: {
  grid: DashboardLayout['grid']
  width: number
}) {
  const [marginX, marginY] = grid.margin
  const colPitch = width > 0 ? (width - marginX) / grid.cols : 0
  const rowPitch = grid.rowHeight + marginY
  const line = 'color-mix(in srgb, var(--color-line-strong) 45%, transparent)'
  const style = width > 0
    ? {
        backgroundImage:
          `repeating-linear-gradient(to right, ${line} 0 1px, transparent 1px ${colPitch}px),` +
          `repeating-linear-gradient(to bottom, ${line} 0 1px, transparent 1px ${rowPitch}px)`,
        backgroundPosition: `${marginX}px 0, 0 ${marginY}px`,
      }
    : undefined
  return (
    <div
      data-testid="edit-grid-overlay"
      className="pointer-events-none absolute inset-0 rounded"
      style={style}
    />
  )
}

export function DashboardGrid({
  layout,
  editing,
  onLayoutChange,
  onWidgetChange,
  onRemove,
  droppingType,
  onDropWidget,
}: {
  layout: DashboardLayout
  editing: boolean
  onLayoutChange?: (l: DashboardLayout) => void
  onWidgetChange?: (w: WidgetInstance) => void
  onRemove?: (id: string) => void
  droppingType?: WidgetType | null
  onDropWidget?: (pos: { x: number; y: number }) => void
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
  // Largura medida do container, para alinhar a grade de fundo ao passo real
  // das colunas do react-grid-layout (que tambem mede a largura do mesmo no).
  const containerRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

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
    <div ref={containerRef} className={`relative${editing ? ' dashboard-grid-editing' : ''}`}>
      {editing && <EditGridOverlay grid={layout.grid} width={width} />}
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
        isDroppable={editing}
        droppingItem={
          droppingType
            ? {
                i: '__dropping__',
                w: WIDGET_REGISTRY[droppingType].defaultSize.w,
                h: WIDGET_REGISTRY[droppingType].defaultSize.h,
              }
            : undefined
        }
        onDrop={(_layout, item) => {
          if (item) onDropWidget?.({ x: item.x, y: item.y })
        }}
      >
        {layout.widgets.map((w, i) => (
          // O div externo (chave do react-grid-layout) recebe do RGL um
          // style inline com transform: translate(x,y) para posicionar o
          // item na grade (useCSSTransforms). Uma animacao CSS de `transform`
          // nesse MESMO no venceria a cascata sobre esse inline style (regra
          // de animacoes) e, com fill-mode:both, prenderia o widget na
          // origem apos o mount. Por isso a classe de entrada (que anima
          // transform) fica num wrapper interno, nao posicionado pelo RGL.
          <div key={w.id}>
            <div
              className="widget-enter h-full w-full motion-reduce:animate-none"
              style={{ animationDelay: `${i * 70}ms` }}
            >
              <WidgetFrame
                widget={w}
                editing={editing}
                onChange={onWidgetChange}
                onRemove={onRemove ? () => onRemove(w.id) : undefined}
              />
            </div>
          </div>
        ))}
      </ResponsiveGridLayout>
    </div>
  )
}
