import type { WidgetInstance, WidgetType } from '../layout/schema'
import { WIDGET_REGISTRY } from './registry'

export function newWidget(type: WidgetType, existing: WidgetInstance[]): WidgetInstance {
  const desc = WIDGET_REGISTRY[type]
  const n = existing.filter((w) => w.type === type).length + 1
  const maxY = existing.reduce((m, w) => Math.max(m, w.layout.y + w.layout.h), 0)
  return {
    id: `${type}-${n}-${maxY}`,
    type,
    layout: {
      x: 0,
      y: maxY,
      w: desc.defaultSize.w,
      h: desc.defaultSize.h,
      minW: desc.minSize.w,
      minH: desc.minSize.h,
    },
    binding: {},
    options: type === 'alarms' ? { scope: 'site' } : {},
  }
}
