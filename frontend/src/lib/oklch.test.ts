import { describe, it, expect } from 'vitest'
import { oklchToRgb, resolveOklchColor } from './oklch'

function parseRgb(s: string): [number, number, number] {
  const m = /rgb\((\d+), (\d+), (\d+)\)/.exec(s)
  if (!m) throw new Error(`nao é rgb(): ${s}`)
  return [Number(m[1]), Number(m[2]), Number(m[3])]
}

describe('oklchToRgb', () => {
  it('preto e branco nos extremos de L', () => {
    expect(oklchToRgb(0, 0, 0)).toBe('rgb(0, 0, 0)')
    expect(oklchToRgb(1, 0, 0)).toBe('rgb(255, 255, 255)')
  })

  it('oklch do vermelho puro sRGB (referencia conhecida) cai perto de rgb(255,0,0)', () => {
    // oklch(62.8% 0.2577 29.23) e a conversao canonica publicada de #ff0000.
    const [r, g, b] = parseRgb(oklchToRgb(0.6279554238, 0.2576833077, 29.2338851923))
    expect(r).toBeGreaterThanOrEqual(253)
    expect(g).toBeLessThanOrEqual(2)
    expect(b).toBeLessThanOrEqual(2)
  })

  it('formato de saida e sempre rgb(r, g, b) pintavel em canvas — nunca oklch()', () => {
    const out = oklchToRgb(0.55, 0.19, 25)
    expect(out).toMatch(/^rgb\(\d+, \d+, \d+\)$/)
    expect(out).not.toContain('oklch')
    expect(out).not.toContain('var(')
  })
})

describe('resolveOklchColor', () => {
  it('converte a string oklch(...) usada em index.css (token --color-crit claro)', () => {
    expect(resolveOklchColor('oklch(0.55 0.19 25)')).toMatch(/^rgb\(\d+, \d+, \d+\)$/)
  })

  it('token --color-crit muda de valor entre claro e escuro -> cores resolvidas diferentes', () => {
    const light = resolveOklchColor('oklch(0.55 0.19 25)')
    const dark = resolveOklchColor('oklch(0.68 0.20 25)')
    expect(light).not.toBe(dark)
  })

  it('string que nao e oklch() passa inalterada (fallback defensivo)', () => {
    expect(resolveOklchColor('rgb(1, 2, 3)')).toBe('rgb(1, 2, 3)')
    expect(resolveOklchColor('')).toBe('')
  })
})
