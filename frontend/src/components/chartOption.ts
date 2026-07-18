import type { EChartsOption } from 'echarts'
import type { HistoryResponse, Threshold } from '../lib/types'

export function buildChartOption(
  history: HistoryResponse | undefined,
  threshold: Threshold | null,
  // ECharts desenha em <canvas> e NAO resolve custom properties CSS — precisa
  // receber a cor ja resolvida (ex.: getComputedStyle(...).getPropertyValue).
  // Default mantem o valor anterior (var(--color-crit)) so para nao quebrar
  // chamadores/testes existentes que nao passam cor; em runtime real o
  // chamador (TimeSeriesChart) sempre resolve e passa o valor concreto.
  critColor: string = 'var(--color-crit)',
): EChartsOption {
  const data: [number, number][] = history
    ? history.points.map((p) => [p.ts, 'value' in p ? p.value : p.avg])
    : []
  const markLine = threshold
    ? {
        symbol: 'none',
        lineStyle: { type: 'dashed' as const, color: critColor },
        data: [{ yAxis: threshold.limite_min }, { yAxis: threshold.limite_max }],
      }
    : undefined
  return {
    grid: { left: 40, right: 16, top: 16, bottom: 28 },
    xAxis: { type: 'time' as const },
    yAxis: { type: 'value' as const, scale: true },
    series: [{ type: 'line' as const, showSymbol: false, data, markLine }],
  }
}
