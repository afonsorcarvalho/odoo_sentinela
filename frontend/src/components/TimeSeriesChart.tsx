import { useEffect, useRef } from 'react'
import { useECharts } from './useECharts'
import { buildChartOption } from './chartOption'
import { useThemeColor } from '../lib/useThemeColor'
import type { HistoryResponse, Threshold, LivePoint } from '../lib/types'

// Teto de pontos ao vivo anexados (appendData) desde o ultimo setOption da
// serie base. Nao limita quantos pontos ficam visiveis (isso e useLiveTail,
// max=300) — limita o crescimento MONOTONICO da serie dentro do ECharts,
// que so cresce via appendData e nunca encolhe sozinha. Sem este teto, uma
// sessao aberta por horas acumula ~86k pontos/dia no chart. O rebuild via
// setOption abaixo e OCASIONAL (a cada ~600 pontos, nao por ponto), entao
// nao quebra a prova de "appendData por ponto, sem setOption por ponto".
const MAX_LIVE_POINTS = 600

export function TimeSeriesChart({
  history, threshold, tail,
}: { history: HistoryResponse | undefined; threshold: Threshold | null; tail: LivePoint[] }) {
  const { el, chart } = useECharts()
  // Cursor de append: ultimo timestamp ja anexado (nao o length de `tail`).
  // `tail` (useLiveTail) e um buffer deslizante com tamanho maximo (slice
  // no mais antigo) — apos encher, tail.length fica constante e um cursor
  // por indice/length trava para sempre. ts e estritamente crescente
  // (garantido por liveApi), entao e um cursor seguro e estavel ao slide.
  const lastTs = useRef<number>(-Infinity)
  // Contador de pontos ao vivo anexados desde o ultimo setOption da serie
  // base — dispara o trim ocasional (ver MAX_LIVE_POINTS acima).
  const liveCountSinceBase = useRef(0)
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
    lastTs.current = -Infinity
    liveCountSinceBase.current = 0
  }, [history, threshold, critColor, chart])

  // Cauda ao vivo: anexa só os pontos novos (appendData), sem refazer a série base.
  useEffect(() => {
    if (!chart.current) return
    const fresh = tail.filter((p) => p.ts > lastTs.current)
    if (fresh.length) {
      chart.current.appendData({ seriesIndex: 0, data: fresh.map((p) => [p.ts, p.value]) })
      lastTs.current = fresh[fresh.length - 1].ts
      liveCountSinceBase.current += fresh.length

      // Trim ocasional: a serie no ECharts so cresce via appendData e nunca
      // encolhe sozinha. A cada MAX_LIVE_POINTS pontos anexados, refazemos a
      // serie base (setOption unico) a partir do snapshot `history` — isto
      // e uma janela movel ocasional (a cada ~600 pontos), NAO por ponto,
      // entao a prova de append-por-ponto continua valendo. Zeramos o
      // cursor para que a `tail` atual (ate 300 pontos) reanexe no proximo
      // efeito, sem perder nem reenviar pontos.
      if (liveCountSinceBase.current > MAX_LIVE_POINTS) {
        chart.current.setOption(buildChartOption(history, threshold, critColor))
        lastTs.current = -Infinity
        liveCountSinceBase.current = 0
      }
    }
  }, [tail, chart])

  return <div ref={el} style={{ width: '100%', height: 320 }} />
}
