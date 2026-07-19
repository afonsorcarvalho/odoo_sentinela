import { useEffect } from 'react'
import { useECharts } from './useECharts'
import { buildChartOption } from './chartOption'
import { useThemeColor } from '../lib/useThemeColor'
import type { HistoryResponse, Threshold, LivePoint } from '../lib/types'

// A prova arquitetural desta tela: a serie historica e buscada UMA vez
// (historyApi.getHistory, cacheada por TanStack Query) e a cauda ao vivo e
// anexada LOCALMENTE — a serie desenhada e `historico (cache) + tail (memoria
// de useLiveTail)`. Nenhum tick ao vivo dispara refetch de historico (provado
// no teste de pagina que espia getHistory). ECharts `appendData` so suporta
// series `scatter`/`lines`, entao a cauda entra via setOption com dados ja
// mesclados por buildChartOption — custo ~1000 pontos/tick, trivial, e a cauda
// (useLiveTail) e limitada a 300, entao a serie nunca cresce sem limite.
export function TimeSeriesChart({
  history, threshold, tail,
}: { history: HistoryResponse | undefined; threshold: Threshold | null; tail: LivePoint[] }) {
  const { el, chart } = useECharts()
  // ECharts pinta em canvas e nao resolve var(--color-crit) — resolvemos aqui
  // (ver useThemeColor) e passamos o valor concreto para buildChartOption.
  const critColor = useThemeColor('--color-crit')
  // Idem para a cor da faixa de conformidade (markArea).
  const goodSoftColor = useThemeColor('--color-good-soft')

  useEffect(() => {
    chart.current?.setOption(buildChartOption(history, threshold, critColor, goodSoftColor, tail), { notMerge: true })
  }, [history, threshold, critColor, goodSoftColor, tail, chart])

  return <div ref={el} style={{ width: '100%', height: '100%', minHeight: 160 }} />
}
