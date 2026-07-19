import { z } from 'zod'

export const WIDGET_TYPES = ['area', 'timeseries', 'alarms', 'kpi'] as const
export type WidgetType = (typeof WIDGET_TYPES)[number]

const widgetLayoutSchema = z.object({
  x: z.number(),
  y: z.number(),
  w: z.number(),
  h: z.number(),
  minW: z.number().optional(),
  minH: z.number().optional(),
})

const widgetInstanceSchema = z.object({
  id: z.string(),
  type: z.enum(WIDGET_TYPES),
  layout: widgetLayoutSchema,
  binding: z.object({
    areaCode: z.string().optional(),
    sensorCode: z.string().optional(),
  }),
  options: z.record(z.string(), z.unknown()).optional().default({}),
})

const dashboardLayoutSchema = z.object({
  version: z.literal(1),
  grid: z.object({
    cols: z.number(),
    rowHeight: z.number(),
    margin: z.tuple([z.number(), z.number()]),
  }),
  widgets: z.array(widgetInstanceSchema),
})

export type WidgetInstance = z.infer<typeof widgetInstanceSchema>
export type DashboardLayout = z.infer<typeof dashboardLayoutSchema>

// Ponto de extensão para versões futuras do schema. Hoje (v1) é no-op.
export function migrate(raw: unknown): unknown {
  return raw
}

export function parseLayout(raw: unknown): DashboardLayout | null {
  const result = dashboardLayoutSchema.safeParse(migrate(raw))
  return result.success ? result.data : null
}
