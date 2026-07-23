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

// options por tipo — `.catch(default)` por campo cobre tanto AUSENTE (backward-compat)
// quanto INVÁLIDO (blob editado à mão) sem lançar — degrada campo a campo.
const timeseriesOptions = z.object({
  defaultWindow: z.enum(['1h', '24h', '7d', '30d']).catch('24h'),
})
const kpiOptions = z
  .object({
    label: z.string().optional().catch(undefined),
    limiteMin: z.number().optional().catch(undefined), // override display-only (§KPI)
    limiteMax: z.number().optional().catch(undefined), // NUNCA suaviza alarm_state
    casasDecimais: z.number().int().min(0).max(6).optional().catch(undefined), // nº fixo de decimais; ausente = auto
    digitosInteiros: z.number().int().min(1).max(12).optional().catch(undefined), // zero-pad mín. da parte inteira
  })
  .refine(
    (o) => o.limiteMin == null || o.limiteMax == null || o.limiteMin <= o.limiteMax,
    { message: 'limiteMin deve ser ≤ limiteMax' },
  )
const alarmsOptions = z.object({
  scope: z.enum(['site', 'area']).catch('site'),
  // areaCode do escopo mora no binding.areaCode (já existe), não aqui
})
const areaOptions = z.object({}) // sem config em B2; strip descarta chaves desconhecidas

export const OPTIONS_SCHEMA = {
  timeseries: timeseriesOptions,
  kpi: kpiOptions,
  alarms: alarmsOptions,
  area: areaOptions,
} satisfies Record<WidgetType, z.ZodTypeAny>

// Parse de options que NUNCA lança: option-set inválido (incl. refine do kpi falhando,
// ex. limiteMin>limiteMax num blob editado à mão) cai nos defaults daquele tipo.
function parseOptions(type: WidgetType, raw: unknown): Record<string, unknown> {
  const schema = OPTIONS_SCHEMA[type]
  const r = schema.safeParse(raw ?? {})
  return (r.success ? r.data : schema.parse({})) as Record<string, unknown> // schema.parse({}) é seguro: só defaults, refine passa
}

const widgetInstanceSchema = z
  .object({
    id: z.string(),
    type: z.enum(WIDGET_TYPES),
    layout: widgetLayoutSchema,
    binding: z.object({
      areaCode: z.string().optional(), // legado (single) — mantido p/ backward-compat
      areaCodes: z.array(z.string()).optional(), // novo: multi-área (alarms scope='area')
      sensorCode: z.string().optional(),
    }),
    options: z.record(z.string(), z.unknown()).optional().default({}),
  })
  .transform((w) => ({ ...w, options: parseOptions(w.type, w.options) as Record<string, unknown> }))

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
