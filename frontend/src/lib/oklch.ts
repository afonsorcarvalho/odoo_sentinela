// Conversao OKLCH -> sRGB (formulas de Bjorn Ottosson, oklab).
//
// Por que converter em vez de so remover o var(): canvas 2D pinta cores
// resolvidas, e o suporte a `oklch()` como valor de fillStyle/strokeStyle
// varia por motor/versao de browser — nao ha como confirmar visualmente
// nesta maquina (sem browser gráfico disponível, ver task-9-report.md).
// Convertendo nos mesmos para `rgb()`, a cor sempre é pintável, em qualquer
// motor de canvas, independente de suporte a oklch() — elimina a duvida em
// vez de assumir suporte.
export function oklchToRgb(l: number, c: number, hDeg: number): string {
  const hRad = (hDeg * Math.PI) / 180
  const a = c * Math.cos(hRad)
  const b = c * Math.sin(hRad)

  const l_ = l + 0.3963377774 * a + 0.2158037573 * b
  const m_ = l - 0.1055613458 * a - 0.0638541728 * b
  const s_ = l - 0.0894841775 * a - 1.2914855480 * b

  const l3 = l_ ** 3
  const m3 = m_ ** 3
  const s3 = s_ ** 3

  const rLin = 4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3
  const gLin = -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3
  const bLin = -0.0041960863 * l3 - 0.7034186147 * m3 + 1.7076147010 * s3

  const toSrgb8 = (v: number): number => {
    const clamped = Math.min(1, Math.max(0, v))
    const s = clamped <= 0.0031308 ? 12.92 * clamped : 1.055 * clamped ** (1 / 2.4) - 0.055
    return Math.round(s * 255)
  }

  return `rgb(${toSrgb8(rLin)}, ${toSrgb8(gLin)}, ${toSrgb8(bLin)})`
}

const OKLCH_RE = /oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)/i

// Converte uma string `oklch(L C H)` (formato usado em src/index.css) para
// `rgb(r, g, b)`. Formatos que nao batem (ja em rgb/hex, ou algo inesperado)
// passam direto — fallback defensivo, nao deve ocorrer com os tokens atuais.
export function resolveOklchColor(raw: string): string {
  const m = OKLCH_RE.exec(raw)
  if (!m) return raw
  const [, l, c, h] = m
  return oklchToRgb(Number(l), Number(c), Number(h))
}
