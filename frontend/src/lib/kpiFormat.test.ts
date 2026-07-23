import { describe, it, expect } from 'vitest'
import { autoCasas, formatKpi } from './kpiFormat'

describe('autoCasas', () => {
  it('inteiro -> 0', () => {
    expect(autoCasas(130)).toBe(0)
    expect(autoCasas(-7)).toBe(0)
  })
  it('detecta casas da fração', () => {
    expect(autoCasas(5.1)).toBe(1)
    expect(autoCasas(19.06)).toBe(2)
  })
  it('cap em 3 casas', () => {
    expect(autoCasas(1.23456)).toBe(3)
  })
})

describe('formatKpi', () => {
  it('sem opts -> auto (idêntico ao comportamento atual)', () => {
    expect(formatKpi(19.063, {})).toBe('19.063')
    expect(formatKpi(130, {})).toBe('130')
    expect(formatKpi(1.23456, {})).toBe('1.235')
  })
  it('casasDecimais fixa as decimais (arredonda)', () => {
    expect(formatKpi(19.063, { casasDecimais: 2 })).toBe('19.06')
    expect(formatKpi(5.1, { casasDecimais: 3 })).toBe('5.100')
    expect(formatKpi(19.063, { casasDecimais: 0 })).toBe('19')
  })
  it('digitosInteiros faz zero-pad da parte inteira', () => {
    expect(formatKpi(19.063, { casasDecimais: 2, digitosInteiros: 3 })).toBe('019.06')
    expect(formatKpi(5.1, { casasDecimais: 1, digitosInteiros: 3 })).toBe('005.1')
    expect(formatKpi(130, { casasDecimais: 0, digitosInteiros: 5 })).toBe('00130')
  })
  it('preserva sinal negativo no zero-pad', () => {
    expect(formatKpi(-5.1, { casasDecimais: 1, digitosInteiros: 3 })).toBe('-005.1')
  })
  it('padding menor que o inteiro presente é no-op (não corta)', () => {
    expect(formatKpi(12345, { casasDecimais: 0, digitosInteiros: 2 })).toBe('12345')
  })
  it('digitosInteiros sem casasDecimais usa auto nas decimais', () => {
    expect(formatKpi(5.1, { digitosInteiros: 3 })).toBe('005.1')
  })
})
