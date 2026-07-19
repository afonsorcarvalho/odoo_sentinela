import type { WidgetInstance, WidgetType } from '../layout/schema'
import { WIDGET_REGISTRY } from './registry'

export function newWidget(
  type: WidgetType,
  existing: WidgetInstance[],
  pos?: { x: number; y: number },
): WidgetInstance {
  const desc = WIDGET_REGISTRY[type]
  const maxY = existing.reduce((m, w) => Math.max(m, w.layout.y + w.layout.h), 0)
  return {
    id: `${type}-${crypto.randomUUID().slice(0, 8)}`,
    type,
    layout: {
      x: pos?.x ?? 0,
      y: pos?.y ?? maxY,
      w: desc.defaultSize.w,
      h: desc.defaultSize.h,
      minW: desc.minSize.w,
      minH: desc.minSize.h,
    },
    binding: {},
    options: type === 'alarms' ? { scope: 'site' } : {},
  }
}
