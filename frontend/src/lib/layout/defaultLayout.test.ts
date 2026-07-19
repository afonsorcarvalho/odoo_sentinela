import { describe, it, expect } from 'vitest'
import { defaultLayout } from './defaultLayout'
import type { AreaGroup } from '../aggregateStatus'

function group(areaCode: string): AreaGroup {
  return { area: { area_code: areaCode, name: areaCode, category: 'cme' }, sensors: [] } as AreaGroup
}

describe('defaultLayout', () => {
  it('gera 1 widget area por grupo + 1 alarms', () => {
    const layout = defaultLayout([group('A'), group('B')])
    const areas = layout.widgets.filter((w) => w.type === 'area')
    const alarms = layout.widgets.filter((w) => w.type === 'alarms')
    expect(areas).toHaveLength(2)
    expect(alarms).toHaveLength(1)
    expect(areas[0].binding.areaCode).toBe('A')
  })
  it('é determinístico', () => {
    expect(defaultLayout([group('A')])).toEqual(defaultLayout([group('A')]))
  })
  it('IDs são estáveis por area_code', () => {
    const l = defaultLayout([group('EXPURGO')])
    expect(l.widgets.find((w) => w.type === 'area')!.id).toContain('EXPURGO')
  })
})
