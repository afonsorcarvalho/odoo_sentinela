import type { EChartsOption } from 'echarts'
import type { HistoryResponse, Threshold, LivePoint } from '../lib/types'

export type Banda = { inicio: number; fim: number; direcao: 'acima' | 'abaixo' }

// Deriva os intervalos de tempo em que a serie plotada esteve fora do
// threshold. Compara o valor JA desenhado (data[i][1]) -- em janela agregada
// isso e o avg, entao toda banda tem excursao visivel da linha por baixo.
// `now` nao entra aqui: a funcao olha so os pontos, e determinista e testavel
// isoladamente (irma de freshness()).
export function computeOutOfRangeBands(
  data: [number, number][],
  threshold: Threshold | null,
): Banda[] {
  if (!threshold || data.length === 0) return []

  const dir = (v: number): 'acima' | 'abaixo' | null =>
    v > threshold.limite_max ? 'acima' : v < threshold.limite_min ? 'abaixo' : null

  // Espacamento mediano entre pontos consecutivos -- referencia para detectar
  // gaps de dado e para estender pontos isolados. Series reais podem ter
  // milhares de pontos; ordenar uma copia dos deltas e barato o suficiente.
  const deltas: number[] = []
  for (let i = 1; i < data.length; i++) deltas.push(data[i][0] - data[i - 1][0])
  const sorted = [...deltas].sort((a, b) => a - b)
  const medianGap = sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0
  const half = medianGap ? medianGap / 2 : 0.5
  const breakGap = medianGap ? medianGap * 3 : Infinity

  const bandas: Banda[] = []
  let run: { startIdx: number; endIdx: number; direcao: 'acima' | 'abaixo' } | null = null

  const flush = () => {
    if (!run) return
    const tStart = data[run.startIdx][0]
    const tEnd = data[run.endIdx][0]
    // Estende cada extremo 1/2 ate o vizinho de dentro; sem vizinho, usa half.
    const prevTs = run.startIdx > 0 ? data[run.startIdx - 1][0] : tStart - medianGap
    const nextTs = run.endIdx < data.length - 1 ? data[run.endIdx + 1][0] : tEnd + medianGap
    const inicio = tStart - Math.min(half, (tStart - prevTs) / 2 || half)
    const fim = tEnd + Math.min(half, (nextTs - tEnd) / 2 || half)
    bandas.push({ inicio, fim, direcao: run.direcao })
    run = null
  }

  for (let i = 0; i < data.length; i++) {
    const d = dir(data[i][1])
    if (d === null) {
      flush()
      continue
    }
    const gapFromPrev = run ? data[i][0] - data[run.endIdx][0] : 0
    if (run && (run.direcao !== d || gapFromPrev > breakGap)) {
      flush()
    }
    if (!run) {
      run = { startIdx: i, endIdx: i, direcao: d }
    } else {
      run.endIdx = i
    }
  }
  flush()
  return bandas
}

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
        // Label do limite DENTRO da area de plot (insideEndTop): o default
        // 'end' fica no fim do eixo, fora do grid, e era clipado pelo
        // overflow-hidden do card. 'inside...' garante que nunca vaza.
        label: { position: 'insideEndTop' as const, color: critColor, fontSize: 10 },
        data: [{ yAxis: threshold.limite_min }, { yAxis: threshold.limite_max }],
      }
    : undefined

  const markArea = threshold
    ? {
        itemStyle: { color: goodSoftColor, opacity: 0.5 },
        // markArea 2D espera pares [inicio, fim]; tipar como tupla p/ o TS não
        // inferir array de tamanho variável (MarkArea2DDataItemOption exige 2).
        data: [[{ yAxis: threshold.limite_min }, { yAxis: threshold.limite_max }]] as [
          { yAxis: number },
          { yAxis: number },
        ][],
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
    // containLabel: ECharts reserva o espaco dos labels dos eixos DENTRO do
    // grid, entao left/bottom nao precisam ser chutados (44px cortava labels
    // Y mais largos, ex.: "50.07"). left/right/top/bottom viram so a folga.
    grid: { left: 8, right: 14, top: 22, bottom: 8, containLabel: true },
    xAxis: { type: 'time' as const },
    yAxis: { type: 'value' as const, scale: true, min: yMin, max: yMax },
    series: [{ type: 'line' as const, showSymbol: false, data, markLine, markArea }],
  }
}
