import type { EChartsOption } from 'echarts'
import type { Granularidade, ReportSensor } from '../lib/api/contracts'

// Rotulo do bucket a partir do ISO local (ja com offset de Sao Paulo): lemos
// os campos direto da string, sem passar por Date, para nao depender do fuso
// do navegador.
export function rotuloBucket(iso: string, gran: Granularidade): string {
  const [data, hora = ''] = iso.split('T')
  const [y, m, d] = data.split('-')
  if (gran === 'hora') return hora.slice(0, 5)
  if (gran === 'dia') return `${d}/${m}`
  return `${m}/${y}`
}

// Linha da media (null em bucket nao-ok -> gap, connectNulls:false) + faixa
// min-max como area empilhada (min transparente + max-min). Dados completos
// via setOption: appendData nao funciona com series 'line'.
export function buildReportChartOption(
  s: ReportSensor,
  gran: Granularidade,
  colors: { crit?: string; primary?: string; muted?: string } = {},
): EChartsOption {
  const ok = (v: number | null, estado: string) => (estado === 'ok' ? v : null)
  const avg = s.buckets.map((b) => ok(b.avg, b.estado))
  const min = s.buckets.map((b) => ok(b.min, b.estado))
  const max = s.buckets.map((b) => ok(b.max, b.estado))
  const faixa = s.buckets.map((b) =>
    b.estado === 'ok' && b.min != null && b.max != null ? +(b.max - b.min).toFixed(6) : null,
  )
  const lim = s.limites
  const linhas = lim
    ? [
        ...(lim.limite_min != null ? [{ yAxis: lim.limite_min, name: 'mín' }] : []),
        ...(lim.limite_max != null ? [{ yAxis: lim.limite_max, name: 'máx' }] : []),
      ]
    : []
  const fmt = (v: unknown) => (typeof v === 'number' ? v.toLocaleString('pt-BR') : '—')

  return {
    animation: false,
    grid: { left: 48, right: 72, top: 28, bottom: 28 },
    legend: { data: ['Máximo', 'Média', 'Mínimo'], top: 0, itemHeight: 8, textStyle: { color: colors.muted } },
    tooltip: { trigger: 'axis', valueFormatter: fmt },
    xAxis: { type: 'category', data: s.buckets.map((b) => rotuloBucket(b.bucket, gran)), boundaryGap: false },
    yAxis: { type: 'value', scale: true, name: s.unidade, axisLabel: { formatter: (v: number) => v.toLocaleString('pt-BR') } },
    series: [
      { name: 'min', type: 'line', stack: 'faixa', data: min, symbol: 'none', lineStyle: { opacity: 0 }, connectNulls: false, tooltip: { show: false } },
      {
        name: 'faixa', type: 'line', stack: 'faixa', data: faixa, symbol: 'none', lineStyle: { opacity: 0 },
        areaStyle: { color: colors.primary, opacity: 0.15 }, connectNulls: false, tooltip: { show: false },
      },
      // Mesmas cores do PDF (api/relatorio_pdf.py: _COR_MAX/_COR_MIN).
      { name: 'Máximo', type: 'line', data: max, connectNulls: false, symbol: 'none', lineStyle: { color: '#c45a00', width: 1 }, itemStyle: { color: '#c45a00' } },
      { name: 'Mínimo', type: 'line', data: min, connectNulls: false, symbol: 'none', lineStyle: { color: '#2a7f62', width: 1 }, itemStyle: { color: '#2a7f62' } },
      {
        name: 'Média', type: 'line', data: avg, connectNulls: false, showSymbol: avg.length <= 62,
        itemStyle: { color: colors.primary }, lineStyle: { color: colors.primary },
        ...(linhas.length
          ? {
              markLine: {
                symbol: 'none', silent: true, data: linhas,
                lineStyle: { color: colors.crit, type: 'dashed' },
                label: { formatter: (p: { name?: string; value?: unknown }) => `${p.name} ${fmt(p.value)}` },
              },
            }
          : {}),
      },
    ],
  }
}
