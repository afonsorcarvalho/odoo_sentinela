// Formatação numérica do valor KPI. Puro e testável isolado.
// `autoCasas` preserva a heurística histórica do KpiWidget (cap 3 casas).
export function autoCasas(value: number): number {
  if (Number.isInteger(value)) return 0
  const frac = String(value).split('.')[1]
  return Math.min(frac?.length ?? 1, 3)
}

// Formata `value` com um nº fixo de casas decimais (ou auto) e, opcionalmente,
// zero-pad da parte inteira a um mínimo de dígitos. O padding NUNCA corta:
// se a parte inteira já tem mais dígitos que o mínimo, fica como está.
export function formatKpi(
  value: number,
  opts: { casasDecimais?: number; digitosInteiros?: number },
): string {
  const decimais = opts.casasDecimais ?? autoCasas(value)
  const s = value.toFixed(decimais) // produz o sinal '-' quando negativo
  if (opts.digitosInteiros == null) return s

  const negativo = s.startsWith('-')
  const semSinal = negativo ? s.slice(1) : s
  const ponto = semSinal.indexOf('.')
  const inteiro = ponto === -1 ? semSinal : semSinal.slice(0, ponto)
  const fracao = ponto === -1 ? '' : semSinal.slice(ponto) // inclui o '.'
  const inteiroPad = inteiro.padStart(opts.digitosInteiros, '0')
  return (negativo ? '-' : '') + inteiroPad + fracao
}
