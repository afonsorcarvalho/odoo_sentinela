import { describe, it, expect } from 'vitest'
import { computeStatus } from './status'
import type { Threshold } from './types'

const t: Threshold = { sensor_id: 'S1', limite_min: 18, limite_max: 22, is_valor_padrao_regulatorio: true }

describe('computeStatus', () => {
  it('ok no centro da faixa', () => {
    const r = computeStatus(20, t)
    expect(r.state).toBe('ok')
    expect(r.label).toBe('Dentro da faixa')
    expect(r.position).toBeCloseTo(0.5, 5)
  })
  it('warn perto do limite superior', () => {
    expect(computeStatus(21.8, t).state).toBe('warn')
  })
  it('warn perto do limite inferior', () => {
    expect(computeStatus(18.2, t).state).toBe('warn')
  })
  it('crit acima do maximo', () => {
    const r = computeStatus(23, t)
    expect(r.state).toBe('crit')
    expect(r.label).toBe('Fora da faixa')
    expect(r.position).toBe(1) // clamp
  })
  it('crit abaixo do minimo', () => {
    expect(computeStatus(17, t).position).toBe(0) // clamp
  })
  it('unknown sem threshold', () => {
    const r = computeStatus(20, null)
    expect(r.state).toBe('unknown')
    expect(r.position).toBeNull()
  })
  it('warn em boundary exato inferior (raw=0.1)', () => {
    // value=18.4: raw = (18.4-18)/4 = 0.1, exatamente na margem
    const r = computeStatus(18.4, t)
    expect(r.state).toBe('warn')
  })
  it('warn em boundary exato superior (raw=0.9)', () => {
    // value=21.6: raw = (21.6-18)/4 = 0.9, exatamente na margem
    const r = computeStatus(21.6, t)
    expect(r.state).toBe('warn')
  })
})
