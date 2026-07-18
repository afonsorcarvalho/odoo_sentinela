import type { EChartsOption } from 'echarts'
import type { HistoryResponse, Threshold } from '../lib/types'

export function buildChartOption(
  history: HistoryResponse | undefined,
  threshold: Threshold | null,
): EChartsOption {
  const data: [number, number][] = history
    ? history.points.map((p) => [p.ts, 'value' in p ? p.value : p.avg])
    : []
  const markLine = threshold
    ? {
        symbol: 'none',
        lineStyle: { type: 'dashed' as const, color: 'var(--color-crit)' },
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
