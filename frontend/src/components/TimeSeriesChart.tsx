import { useEffect, useRef } from 'react'
import { useECharts } from './useECharts'
import { buildChartOption } from './chartOption'
import { useThemeColor } from '../lib/useThemeColor'
import type { HistoryResponse, Threshold, LivePoint } from '../lib/types'

export function TimeSeriesChart({
  history, threshold, tail,
}: { history: HistoryResponse | undefined; threshold: Threshold | null; tail: LivePoint[] }) {
  const { el, chart } = useECharts()
  const appended = useRef(0)
  // ECharts pinta em canvas e nao resolve var(--color-crit) — resolvemos aqui
  // (ver useThemeColor) e passamos o valor concreto para buildChartOption.
  const critColor = useThemeColor('--color-crit')

  // Série base: só quando histórico/threshold/cor mudam (setOption). Reseta o
  // cursor de append.
  //
  // Nota de coordenação tail/janela/tema: trocar a janela (novo `history`) OU
  // trocar o tema (novo `critColor`, ex.: crit claro -> crit escuro) refaz a
  // série base e zera `appended`. Isso NAO derruba a cauda ao vivo: os pontos
  // continuam acumulados em `tail` (estado de useLiveTail, que não é afetado
  // por nenhum dos dois). No pior caso, o próximo tick ao vivo (useEffect
  // abaixo, que só reage a mudanças de `tail`) reanexa de uma vez todos os
  // pontos já acumulados, porque o cursor foi para 0 — ou seja, pode haver um
  // frame sem cauda visível até o próximo tick, mas ela sempre volta e
  // nenhum ponto é perdido nem reenviado.
  useEffect(() => {
    chart.current?.setOption(buildChartOption(history, threshold, critColor))
    appended.current = 0
  }, [history, threshold, critColor, chart])

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
