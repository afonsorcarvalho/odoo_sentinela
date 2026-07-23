import { describe, it, expect } from 'vitest'
import { parseLayout, migrate, OPTIONS_SCHEMA } from './schema'

const validLayout = {
  version: 1,
  grid: { cols: 12, rowHeight: 40, margin: [8, 8] },
  widgets: [
    { id: 'w1', type: 'kpi', layout: { x: 0, y: 0, w: 2, h: 2 }, binding: { sensorCode: 'S1' }, options: {} },
  ],
}

describe('parseLayout', () => {
  it('aceita layout válido', () => {
    expect(parseLayout(validLayout)).toEqual(validLayout)
  })
  it('devolve null para não-objeto', () => {
    expect(parseLayout('nope')).toBeNull()
    expect(parseLayout(null)).toBeNull()
  })
  it('devolve null quando widget tem type desconhecido', () => {
    const bad = { ...validLayout, widgets: [{ ...validLayout.widgets[0], type: 'foo' }] }
    expect(parseLayout(bad)).toBeNull()
  })
  it('devolve null quando falta layout.x', () => {
    const bad = { ...validLayout, widgets: [{ ...validLayout.widgets[0], layout: { y: 0, w: 2, h: 2 } }] }
    expect(parseLayout(bad)).toBeNull()
  })
})

describe('migrate', () => {
  it('é no-op para version 1', () => {
    expect(migrate(validLayout)).toEqual(validLayout)
  })
})

describe('OPTIONS_SCHEMA', () => {
  it('timeseries: aplica defaultWindow default quando options ausente/vazio', () => {
    expect(OPTIONS_SCHEMA.timeseries.parse({})).toEqual({ defaultWindow: '24h' })
  })

  it('timeseries: defaultWindow inválido cai no default 24h', () => {
    expect(OPTIONS_SCHEMA.timeseries.parse({ defaultWindow: 'nope' })).toEqual({
      defaultWindow: '24h',
    })
  })

  it('timeseries: defaultWindow válido é preservado', () => {
    expect(OPTIONS_SCHEMA.timeseries.parse({ defaultWindow: '7d' })).toEqual({
      defaultWindow: '7d',
    })
  })

  it('alarms: aplica scope default quando ausente/vazio', () => {
    expect(OPTIONS_SCHEMA.alarms.parse({})).toEqual({ scope: 'site' })
  })

  it('alarms: scope inválido cai no default site', () => {
    expect(OPTIONS_SCHEMA.alarms.parse({ scope: 'nope' })).toEqual({ scope: 'site' })
  })

  it('area: schema vazio, aceita e descarta chaves desconhecidas', () => {
    expect(OPTIONS_SCHEMA.area.parse({ qualquerCoisa: 1 })).toEqual({})
  })

  it('kpi: defaults quando ausente/vazio', () => {
    expect(OPTIONS_SCHEMA.kpi.parse({})).toEqual({
      label: undefined,
      limiteMin: undefined,
      limiteMax: undefined,
      casasDecimais: undefined,
      digitosInteiros: undefined,
    })
  })

  it('kpi: casasDecimais e digitosInteiros válidos são preservados', () => {
    const r = OPTIONS_SCHEMA.kpi.parse({ casasDecimais: 2, digitosInteiros: 3 })
    expect(r).toMatchObject({ casasDecimais: 2, digitosInteiros: 3 })
  })
  it('kpi: casasDecimais fora do range vira undefined (catch)', () => {
    expect(OPTIONS_SCHEMA.kpi.parse({ casasDecimais: 99 }).casasDecimais).toBeUndefined()
    expect(OPTIONS_SCHEMA.kpi.parse({ casasDecimais: -1 }).casasDecimais).toBeUndefined()
  })
  it('kpi: digitosInteiros inválido (0 ou string) vira undefined (catch)', () => {
    expect(OPTIONS_SCHEMA.kpi.parse({ digitosInteiros: 0 }).digitosInteiros).toBeUndefined()
    expect(OPTIONS_SCHEMA.kpi.parse({ digitosInteiros: 'x' as unknown as number }).digitosInteiros).toBeUndefined()
  })

  it('kpi refine (schema isolado): limiteMin > limiteMax reprova (success:false)', () => {
    const r = OPTIONS_SCHEMA.kpi.safeParse({ limiteMin: 10, limiteMax: 5 })
    expect(r.success).toBe(false)
  })

  it('kpi refine (schema isolado): só limiteMin preenchido é válido', () => {
    const r = OPTIONS_SCHEMA.kpi.safeParse({ limiteMin: 10 })
    expect(r.success).toBe(true)
  })

  it('kpi refine (schema isolado): só limiteMax preenchido é válido', () => {
    const r = OPTIONS_SCHEMA.kpi.safeParse({ limiteMax: 20 })
    expect(r.success).toBe(true)
  })

  it('kpi refine (schema isolado): limiteMin <= limiteMax é válido', () => {
    const r = OPTIONS_SCHEMA.kpi.safeParse({ limiteMin: 5, limiteMax: 10 })
    expect(r.success).toBe(true)
  })
})

describe('parseLayout — options por tipo (transform em runtime)', () => {
  it('timeseries: defaultWindow inválido no blob não derruba o layout, cai no default', () => {
    const raw = {
      ...validLayout,
      widgets: [
        {
          id: 'w1',
          type: 'timeseries',
          layout: { x: 0, y: 0, w: 2, h: 2 },
          binding: { sensorCode: 'S1' },
          options: { defaultWindow: 'invalido' },
        },
      ],
    }
    const result = parseLayout(raw)
    expect(result).not.toBeNull()
    expect(result?.widgets[0].options).toEqual({ defaultWindow: '24h' })
  })

  it('alarms: scope inválido no blob não derruba o layout, cai no default', () => {
    const raw = {
      ...validLayout,
      widgets: [
        {
          id: 'w1',
          type: 'alarms',
          layout: { x: 0, y: 0, w: 2, h: 2 },
          binding: {},
          options: { scope: 'invalido' },
        },
      ],
    }
    const result = parseLayout(raw)
    expect(result).not.toBeNull()
    expect(result?.widgets[0].options).toEqual({ scope: 'site' })
  })

  it('kpi: limiteMin > limiteMax NÃO derruba o layout — cai nos defaults do tipo (invariante crítica)', () => {
    const raw = {
      ...validLayout,
      widgets: [
        {
          id: 'w1',
          type: 'kpi',
          layout: { x: 0, y: 0, w: 2, h: 2 },
          binding: { sensorCode: 'S1' },
          options: { limiteMin: 10, limiteMax: 5 },
        },
      ],
    }
    const result = parseLayout(raw)
    expect(result).not.toBeNull()
    expect(result?.widgets[0].options).toEqual({
      label: undefined,
      limiteMin: undefined,
      limiteMax: undefined,
      casasDecimais: undefined,
      digitosInteiros: undefined,
    })
  })

  it('kpi: limiteMin <= limiteMax válido é preservado via parseLayout', () => {
    const raw = {
      ...validLayout,
      widgets: [
        {
          id: 'w1',
          type: 'kpi',
          layout: { x: 0, y: 0, w: 2, h: 2 },
          binding: { sensorCode: 'S1' },
          options: { limiteMin: 5, limiteMax: 10, label: 'Vazão' },
        },
      ],
    }
    const result = parseLayout(raw)
    expect(result).not.toBeNull()
    expect(result?.widgets[0].options).toEqual({ label: 'Vazão', limiteMin: 5, limiteMax: 10, casasDecimais: undefined, digitosInteiros: undefined })
  })

  it('backward-compat: blob antigo {scope: "site"} parseia e ganha defaults, version continua 1', () => {
    const raw = {
      version: 1,
      grid: { cols: 12, rowHeight: 40, margin: [8, 8] },
      widgets: [
        {
          id: 'w1',
          type: 'alarms',
          layout: { x: 0, y: 0, w: 2, h: 2 },
          binding: {},
          options: { scope: 'site' },
        },
      ],
    }
    const result = parseLayout(raw)
    expect(result).not.toBeNull()
    expect(result?.version).toBe(1)
    expect(result?.widgets[0].options).toEqual({ scope: 'site' })
  })

  it('backward-compat: blob sem options nenhum ganha defaults do tipo', () => {
    const raw = {
      version: 1,
      grid: { cols: 12, rowHeight: 40, margin: [8, 8] },
      widgets: [
        {
          id: 'w1',
          type: 'timeseries',
          layout: { x: 0, y: 0, w: 2, h: 2 },
          binding: { sensorCode: 'S1' },
        },
      ],
    }
    const result = parseLayout(raw)
    expect(result).not.toBeNull()
    expect(result?.widgets[0].options).toEqual({ defaultWindow: '24h' })
  })

  it('binding.areaCodes: array de strings valida', () => {
    const raw = {
      version: 1,
      grid: { cols: 12, rowHeight: 40, margin: [8, 8] },
      widgets: [
        {
          id: 'w1',
          type: 'alarms',
          layout: { x: 0, y: 0, w: 2, h: 2 },
          binding: { areaCodes: ['a', 'b'] },
          options: { scope: 'area' },
        },
      ],
    }
    const result = parseLayout(raw)
    expect(result).not.toBeNull()
    expect(result?.widgets[0].binding).toEqual({ areaCodes: ['a', 'b'] })
  })

  it('binding.areaCodes: ausente é ok (opcional)', () => {
    const raw = {
      version: 1,
      grid: { cols: 12, rowHeight: 40, margin: [8, 8] },
      widgets: [
        {
          id: 'w1',
          type: 'alarms',
          layout: { x: 0, y: 0, w: 2, h: 2 },
          binding: {},
          options: { scope: 'site' },
        },
      ],
    }
    const result = parseLayout(raw)
    expect(result).not.toBeNull()
    expect(result?.widgets[0].binding).toEqual({})
  })

  it('backward-compat: blob antigo com só binding.areaCode (sem areaCodes) parseia, version continua 1', () => {
    const raw = {
      version: 1,
      grid: { cols: 12, rowHeight: 40, margin: [8, 8] },
      widgets: [
        {
          id: 'w1',
          type: 'alarms',
          layout: { x: 0, y: 0, w: 2, h: 2 },
          binding: { areaCode: 'a' },
          options: { scope: 'area' },
        },
      ],
    }
    const result = parseLayout(raw)
    expect(result).not.toBeNull()
    expect(result?.version).toBe(1)
    expect(result?.widgets[0].binding).toEqual({ areaCode: 'a' })
  })
})
