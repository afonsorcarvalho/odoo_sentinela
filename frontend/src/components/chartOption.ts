import type { EChartsOption } from 'echarts'
import type { HistoryResponse, Threshold, LivePoint } from '../lib/types'

export function buildChartOption(
  history: HistoryResponse | undefined,
  threshold: Threshold | null,
  // ECharts desenha em <canvas> e NAO resolve custom properties CSS — precisa
  // receber a cor ja resolvida (ex.: getComputedStyle(...).getPropertyValue).
  // Default mantem o valor anterior (var(--color-crit)) so para nao quebrar
  // chamadores/testes existentes que nao passam cor; em runtime real o
  // chamador (TimeSeriesChart) sempre resolve e passa o valor concreto.
  critColor: string = 'var(--color-crit)',
  // Mesmo motivo do critColor acima: canvas nao resolve var(...), entao a
  // cor da faixa (markArea) tambem precisa vir ja resolvida do chamador.
  goodSoftColor: string = 'var(--color-good-soft)',
  // Cauda ao vivo (buffer local de useLiveTail, ate 300 pontos). Anexada
  // localmente a serie historica, SEM refetch — a serie desenhada e
  // historico (cache) + cauda (memoria). ECharts `appendData` so suporta
  // series `scatter`/`lines`, nao `line`, entao a cauda entra via setOption
  // com os dados ja mesclados (custo O(historico+cauda) ~1000 pts/tick,
  // trivial; nenhuma pressao no banco pois nada e refetchado).
  tail: LivePoint[] = [],
): EChartsOption {
  const histData: [number, number][] = history
    ? history.points.map((p) => [p.ts, 'value' in p ? p.value : p.avg])
    : []
  // Evita sobreposicao: so pontos da cauda mais recentes que o ultimo do historico.
  const lastHistTs = histData.length ? histData[histData.length - 1][0] : -Infinity
  const tailData: [number, number][] = tail
    .filter((p) => p.ts > lastHistTs)
    .map((p) => [p.ts, p.value])
  const data = [...histData, ...tailData]

  const markLine = threshold
    ? {
        symbol: 'none',
        lineStyle: { type: 'dashed' as const, color: critColor },
        data: [{ yAxis: threshold.limite_min }, { yAxis: threshold.limite_max }],
      }
    : undefined

  const markArea = threshold
    ? {
        itemStyle: { color: goodSoftColor, opacity: 0.5 },
        data: [[{ yAxis: threshold.limite_min }, { yAxis: threshold.limite_max }]],
      }
    : undefined

  // Eixo Y: garante que as linhas de limite fiquem SEMPRE visiveis (elas sao o
  // ponto do readout de instrumento — ver a leitura relativa a faixa segura).
  // Sem isto, `scale:true` ajusta so aos dados e clipa os limites para fora.
  // Estende para conter [limite_min, limite_max] e tambem qualquer valor lido
  // fora da faixa, com uma folga de 15% da faixa.
  let yMin: number | undefined
  let yMax: number | undefined
  if (threshold) {
    // reduce (nao spread) — series reais nao-decimadas podem ter dezenas de
    // milhares de pontos e `Math.min(...vals)` estouraria a pilha de argumentos.
    const lo = data.reduce((acc, d) => Math.min(acc, d[1]), threshold.limite_min)
    const hi = data.reduce((acc, d) => Math.max(acc, d[1]), threshold.limite_max)
    const pad = (threshold.limite_max - threshold.limite_min) * 0.15 || 1
    yMin = lo - pad
    yMax = hi + pad
  }

  return {
    animation: false,
    grid: { left: 44, right: 16, top: 16, bottom: 28 },
    xAxis: { type: 'time' as const },
    yAxis: { type: 'value' as const, scale: true, min: yMin, max: yMax },
    series: [{ type: 'line' as const, showSymbol: false, data, markLine, markArea }],
  }
}
