import { useEffect, useRef } from 'react'
import { useECharts } from './useECharts'
import { buildChartOption } from './chartOption'
import type { HistoryResponse, Threshold, LivePoint } from '../lib/types'

export function TimeSeriesChart({
  history, threshold, tail,
}: { history: HistoryResponse | undefined; threshold: Threshold | null; tail: LivePoint[] }) {
  const { el, chart } = useECharts()
  const appended = useRef(0)

  // Série base: só quando histórico/threshold mudam (setOption). Reseta o cursor de append.
  useEffect(() => {
    chart.current?.setOption(buildChartOption(history, threshold))
    appended.current = 0
  }, [history, threshold, chart])

  // Cauda ao vivo: anexa só os pontos novos (appendData), sem refazer a série base.
  useEffect(() => {
    if (!chart.current) return
    for (let i = appended.current; i < tail.length; i++) {
      chart.current.appendData({ seriesIndex: 0, data: [[tail[i].ts, tail[i].value]] })
    }
    appended.current = tail.length
  }, [tail, chart])

  return <div ref={el} style={{ width: '100%', height: 320 }} />
}
