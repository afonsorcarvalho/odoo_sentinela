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
  history, threshold, tail, status, now,
}: {
  history: HistoryResponse | undefined
  threshold: Threshold | null
  tail: LivePoint[]
  // Estado do fetch de historico, para distinguir "sem dados no periodo" de
  // "carregando" e de "falha". Opcional: chamadores que nao passam mantem o
  // comportamento anterior (empty-state generico quando nao ha pontos).
  status?: 'loading' | 'error'
  now?: number
}) {
  const { el, chart } = useECharts()
  // ECharts pinta em canvas e nao resolve var(--color-crit) — resolvemos aqui
  // (ver useThemeColor) e passamos o valor concreto para buildChartOption.
  const critColor = useThemeColor('--color-crit')
  // Idem para a cor da faixa de conformidade (markArea).
  const goodSoftColor = useThemeColor('--color-good-soft')
  // Idem para a cor da faixa de silencio (sem dado ha mais que o stale).
  const mutedColor = useThemeColor('--color-muted')

  useEffect(() => {
    chart.current?.setOption(
      buildChartOption(history, threshold, critColor, goodSoftColor, tail, now, mutedColor),
      { notMerge: true },
    )
  }, [history, threshold, critColor, goodSoftColor, tail, now, mutedColor, chart])

  // Precedencia: pontos presentes > carregando > falha > vazio. Dado presente
  // sempre vence (TanStack mantem `data` num refetch que falha, entao nao
  // apagamos um grafico que tem dado). Empty-state so quando nao ha ponto algum.
  const hasPoints = !!history && history.points.length > 0
  const emptyMessage = hasPoints
    ? null
    : status === 'loading'
      ? 'Carregando…'
      : status === 'error'
        ? 'Falha ao carregar o histórico'
        : 'Sem dados no período'

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', minHeight: 160 }}>
      {/* Div do canvas mantido montado sempre (mesmo no empty-state): preserva
          a instancia ECharts (init/dispose) e mostra a faixa de conformidade +
          eixos como contexto por tras da mensagem. */}
      <div ref={el} style={{ width: '100%', height: '100%' }} />
      {emptyMessage && (
        <div
          className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm font-medium"
          style={{ color: 'var(--color-muted)' }}
        >
          {emptyMessage}
        </div>
      )}
    </div>
  )
}
