import type { AreaGroup } from '../aggregateStatus'
import type { DashboardLayout, WidgetInstance } from './schema'

const COLS = 12
const AREA_W = 3
const AREA_H = 3

// Layout inicial quando nenhum foi salvo: reproduz o dashboard atual
// (um card por área numa grade + painel de alarmes à direita).
export function defaultLayout(groups: AreaGroup[]): DashboardLayout {
  const perRow = Math.max(1, Math.floor((COLS - AREA_W) / AREA_W)) // deixa espaço p/ alarms
  const widgets: WidgetInstance[] = groups.map((g, i) => ({
    id: `area-${g.area.area_code}`,
    type: 'area',
    layout: {
      x: (i % perRow) * AREA_W,
      y: Math.floor(i / perRow) * AREA_H,
      w: AREA_W,
      h: AREA_H,
    },
    binding: { areaCode: g.area.area_code },
    options: {},
  }))

  widgets.push({
    id: 'alarms-site',
    type: 'alarms',
    layout: { x: COLS - AREA_W, y: 0, w: AREA_W, h: AREA_H * 2 },
    binding: {},
    options: { scope: 'site' },
  })

  return {
    version: 1,
    grid: { cols: COLS, rowHeight: 40, margin: [8, 8] },
    widgets,
  }
}
