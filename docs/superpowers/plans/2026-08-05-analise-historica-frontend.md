# Análise Histórica — Plano B (Frontend) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uma página `/analise` onde o usuário sobrepõe vários sensores da mesma área num gráfico com dois eixos Y e navega o tempo por zoom contínuo, com a resolução do dado trocando sozinha.

**Architecture:** Página nova no SPA, consumindo o contrato `desde/ate/bucket` fechado pelo Plano A. O chart multi-série é um irmão do `TimeSeriesChart`, não uma generalização dele. O estado (área, sensores, intervalo, bucket) mora na URL. Sem cauda ao vivo.

**Tech Stack:** React 19, react-router 8, TanStack Query 5, ECharts 6, Tailwind 4, vitest + testing-library.

**Spec:** `docs/superpowers/specs/2026-08-05-analise-historica-sobreposta-design.md` (Parte B)

**Depende de:** Plano A concluído (`docs/superpowers/plans/2026-08-05-analise-historica-backend.md`). Sem ele, `getHistoryRange` só funciona em modo mock.

## Global Constraints

- **`chartOption.ts` e `TimeSeriesChart.tsx` não são modificados.** Eles carregam markArea de fora-limite, gaps offline, faixa de silêncio e merge da cauda ao vivo — tudo escrito para uma série. Uma regressão em `TimeSeriesChart.test.tsx` é o sinal de que se foi pelo caminho errado.
- **Sem cauda ao vivo** (`useLiveTail`) nesta página. Decisão de escopo da spec, não esquecimento.
- **No máximo duas unidades distintas** no gráfico. A terceira é bloqueada na entrada, com aviso.
- **Sensores sempre da mesma área.**
- As fronteiras da escada vêm de `contrato/escada_resolucao.json`; o teste do frontend lê o mesmo arquivo que o do backend.
- Cor de série nunca reusa token semântico (`--color-crit`, `--color-good`, `--color-warn`): uma série vermelha lê como alarme.
- Português nos comentários e na UI; identificadores seguindo o código existente.

## File Structure

**Criar:**

| Arquivo | Responsabilidade |
|---|---|
| `frontend/src/lib/escolherBucket.ts` | `span (s) → bucket`. Puro. Espelha `api/escada.py`. |
| `frontend/src/lib/escolherBucket.test.ts` | Fronteiras lidas do JSON de contrato |
| `frontend/src/components/multiChartOption.ts` | Option do ECharts para N séries e dois eixos |
| `frontend/src/components/multiChartOption.test.ts` | Eixos, mapeamento e faixa mín–máx |
| `frontend/src/components/MultiSeriesChart.tsx` | Componente do canvas |
| `frontend/src/components/MultiSeriesChart.test.tsx` | Estados de carga/erro/vazio |
| `frontend/src/pages/AnalisePage.tsx` | Seleção, regra das unidades, estado na URL, zoom |
| `frontend/src/pages/AnalisePage.test.tsx` | Comportamento da página |
| `frontend/src/lib/paletaSeries.ts` | Paleta categórica resolvida do tema |

**Modificar:**

| Arquivo | Mudança |
|---|---|
| `frontend/src/lib/types.ts` | `Bucket`, `BucketPedido`, `HistoryRangeResponse` |
| `frontend/src/lib/api/contracts.ts` | `getHistoryRange` no `HistoryApi` |
| `frontend/src/lib/api/real/historyApi.ts` | Implementação real |
| `frontend/src/lib/api/mock/historyApi.ts` | Implementação mock |
| `frontend/src/lib/queries.ts` | `useHistoriesRange` |
| `frontend/src/index.css` | Tokens `--color-serie-1..6` nos dois temas |
| `frontend/src/App.tsx` | Rota `/analise` |
| `frontend/src/components/Topbar.tsx` | Link *Análise* |
| `frontend/src/components/SensorDetailDrawer.tsx` | Botão *Analisar histórico* |

## Como rodar os testes

Do diretório `frontend/`:

```bash
npx vitest run src/lib/escolherBucket.test.ts
npx vitest run                       # suíte inteira, antes de fechar cada task
npx tsc -b --noEmit                  # tipos
```

---

### Task 1: `escolherBucket` no frontend

Precisa existir no cliente para montar a chave de cache **antes** da resposta chegar — é o que faz voltar a um zoom anterior vir do cache em vez da rede.

**Files:**
- Create: `frontend/src/lib/escolherBucket.ts`
- Create: `frontend/src/lib/escolherBucket.test.ts`

**Interfaces:**
- Consumes: `contrato/escada_resolucao.json` (criado no Plano A, Task 1).
- Produces: `escolherBucket(spanSegundos: number): Bucket`, `DEGRAUS: { bucket: Bucket; spanMaxS: number | null }[]`

- [ ] **Step 1: Write the failing test**

Criar `frontend/src/lib/escolherBucket.test.ts`:

```ts
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'
import { escolherBucket, DEGRAUS } from './escolherBucket'

const H = 3600
const D = 86400

describe('escolherBucket', () => {
  it('usa as mesmas fronteiras do contrato lido pelo backend', () => {
    // Vitest roda em node, então lemos o arquivo direto — sem import de JSON
    // fora do root do Vite. As duas implementações (api/escada.py e esta) não
    // podem divergir; este teste é o cadeado.
    const bruto = JSON.parse(
      readFileSync(resolve(__dirname, '../../../contrato/escada_resolucao.json'), 'utf-8'),
    )
    expect(DEGRAUS).toEqual(
      bruto.degraus.map((d: { bucket: string; span_max_s: number | null }) => ({
        bucket: d.bucket,
        spanMaxS: d.span_max_s,
      })),
    )
  })

  it.each([
    [60, 'raw'],
    [3 * H, 'raw'],
    [3 * H + 1, 'minuto'],
    [36 * H, 'minuto'],
    [36 * H + 1, 'hora'],
    [90 * D, 'hora'],
    [90 * D + 1, 'dia'],
    [5 * 365 * D, 'dia'],
    [5 * 365 * D + 1, 'semana'],
    [20 * 365 * D, 'semana'],
    [20 * 365 * D + 1, 'mes'],
  ])('span de %i s -> %s', (span, esperado) => {
    expect(escolherBucket(span)).toBe(esperado)
  })

  it('span zero ou negativo cai no degrau mais fino', () => {
    expect(escolherBucket(0)).toBe('raw')
    expect(escolherBucket(-10)).toBe('raw')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/lib/escolherBucket.test.ts`
Expected: FAIL — `Failed to resolve import "./escolherBucket"`

- [ ] **Step 3: Write minimal implementation**

Acrescentar a `frontend/src/lib/types.ts`:

```ts
export type Bucket = 'raw' | 'minuto' | 'hora' | 'dia' | 'semana' | 'mes'
export type BucketPedido = Bucket | 'auto'

export type RangePoint =
  | { ts: number; value: number }
  | { ts: number; min: number; max: number; avg: number; count: number }

export type HistoryRangeResponse = {
  sensor_code: string
  desde: string
  ate: string
  bucket: Bucket
  resolution: 'raw' | 'agg'
  points: RangePoint[]
}
```

Criar `frontend/src/lib/escolherBucket.ts`:

```ts
import type { Bucket } from './types'

// Espelho de api/escada.py. Os números vivem em contrato/escada_resolucao.json;
// aqui eles são repetidos porque importar JSON de fora do root do Vite
// complica o build sem ganho — o teste lê o arquivo e falha se divergirem.
export const DEGRAUS: { bucket: Bucket; spanMaxS: number | null }[] = [
  { bucket: 'raw', spanMaxS: 10800 },
  { bucket: 'minuto', spanMaxS: 129600 },
  { bucket: 'hora', spanMaxS: 7776000 },
  { bucket: 'dia', spanMaxS: 157680000 },
  { bucket: 'semana', spanMaxS: 630720000 },
  { bucket: 'mes', spanMaxS: null },
]

export function escolherBucket(spanSegundos: number): Bucket {
  for (const degrau of DEGRAUS) {
    if (degrau.spanMaxS === null || spanSegundos <= degrau.spanMaxS) return degrau.bucket
  }
  return DEGRAUS[DEGRAUS.length - 1].bucket
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/lib/escolherBucket.test.ts`
Expected: PASS (13 testes)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/escolherBucket.ts frontend/src/lib/escolherBucket.test.ts frontend/src/lib/types.ts
git commit -m "feat(frontend): escada de resolucao espelhada do contrato"
```

---

### Task 2: Contrato de API e hook de busca

**Files:**
- Modify: `frontend/src/lib/api/contracts.ts`
- Modify: `frontend/src/lib/api/real/historyApi.ts`
- Modify: `frontend/src/lib/api/mock/historyApi.ts`
- Modify: `frontend/src/lib/queries.ts`
- Create: `frontend/src/lib/api/real/historyApi.range.test.ts`

**Interfaces:**
- Consumes: `escolherBucket` (Task 1); endpoint do Plano A.
- Produces:
  - `HistoryApi.getHistoryRange(code: string, desde: number, ate: number, bucket: BucketPedido): Promise<HistoryRangeResponse>` — `desde`/`ate` em epoch ms
  - `useHistoriesRange(codes: string[], desde: number, ate: number, bucket: BucketPedido)` — array de resultados do TanStack, na ordem de `codes`

Epoch ms na fronteira do app e ISO só no adapter: o chart já trabalha em ms, e converter em um lugar só evita fuso perdido no caminho.

- [ ] **Step 1: Write the failing test**

Criar `frontend/src/lib/api/real/historyApi.range.test.ts`:

```ts
import { describe, it, expect, vi, afterEach } from 'vitest'
import { realHistoryApi } from './historyApi'

afterEach(() => { vi.restoreAllMocks() })

describe('realHistoryApi.getHistoryRange', () => {
  it('manda desde/ate em ISO com timezone e o bucket pedido', async () => {
    const corpo = {
      sensor_code: 'SNR-1', desde: '2026-03-10T00:00:00+00:00', ate: '2026-03-10T06:00:00+00:00',
      bucket: 'minuto', resolution: 'agg', points: [],
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(corpo), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    localStorage.setItem('sentinela.token', 'tok')

    const r = await realHistoryApi.getHistoryRange(
      'SNR-1', Date.UTC(2026, 2, 10, 0, 0), Date.UTC(2026, 2, 10, 6, 0), 'auto')

    const url = String(fetchMock.mock.calls[0][0])
    // O backend recusa datetime sem offset com 400 — o adapter é o único lugar
    // que converte, então o Z tem que sair daqui.
    expect(url).toContain('desde=2026-03-10T00%3A00%3A00.000Z')
    expect(url).toContain('ate=2026-03-10T06%3A00%3A00.000Z')
    expect(url).toContain('bucket=auto')
    expect(r.bucket).toBe('minuto')
  })
})
```

Ajustar a chave do `localStorage` para a constante real usada por `real/http.ts` se for outra.

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/lib/api/real/historyApi.range.test.ts`
Expected: FAIL — `realHistoryApi.getHistoryRange is not a function`

- [ ] **Step 3: Write minimal implementation**

Em `frontend/src/lib/api/contracts.ts`, no `HistoryApi`:

```ts
export type HistoryApi = {
  getHistory(code: string, window: Window): Promise<HistoryResponse>
  getHistoryRange(
    code: string, desde: number, ate: number, bucket: BucketPedido,
  ): Promise<HistoryRangeResponse>
}
```

Acrescentar `BucketPedido` e `HistoryRangeResponse` ao import de `../types` no topo do arquivo.

Em `frontend/src/lib/api/real/historyApi.ts`:

```ts
  getHistoryRange(code, desde, ate, bucket) {
    // toISOString() sempre emite Z; o backend recusa datetime sem offset.
    const q = new URLSearchParams({
      desde: new Date(desde).toISOString(),
      ate: new Date(ate).toISOString(),
      bucket,
    })
    return authFetchJson(`/sensores/${code}/historico?${q}`)
  },
```

Em `frontend/src/lib/api/mock/historyApi.ts`, acrescentar ao objeto exportado:

```ts
  async getHistoryRange(sensor_code, desde, ate, bucket): Promise<HistoryRangeResponse> {
    const threshold = THRESHOLDS[sensor_code] ?? THRESHOLD
    const efetivo: Bucket = bucket === 'auto' ? escolherBucket((ate - desde) / 1000) : bucket
    const mid = (threshold.limite_min + threshold.limite_max) / 2
    const amp = (threshold.limite_max - threshold.limite_min) / 3
    const n = 300
    const step = (ate - desde) / n
    const raw = efetivo === 'raw'
    const points: RangePoint[] = []
    for (let i = 0; i < n; i++) {
      const ts = desde + i * step
      const base = mid + amp * Math.sin(i / 12)
      if (raw) points.push({ ts, value: +base.toFixed(2) })
      else points.push({
        ts, min: +(base - amp / 4).toFixed(2), max: +(base + amp / 4).toFixed(2),
        avg: +base.toFixed(2), count: 6,
      })
    }
    return {
      sensor_code, desde: new Date(desde).toISOString(), ate: new Date(ate).toISOString(),
      bucket: efetivo, resolution: raw ? 'raw' : 'agg', points,
    }
  },
```

Com os imports correspondentes (`escolherBucket`, e os tipos `Bucket`, `BucketPedido`, `RangePoint`, `HistoryRangeResponse`).

Em `frontend/src/lib/queries.ts`:

```ts
// Chave inclui o bucket EFETIVO (não 'auto'): voltar a um zoom já visto acerta
// a mesma chave e vem do cache, sem rede. Com 'auto' na chave, dois spans
// diferentes que resolvem para o mesmo bucket disputariam a mesma entrada.
export function useHistoriesRange(
  codes: string[], desde: number, ate: number, bucket: BucketPedido,
) {
  const efetivo = bucket === 'auto' ? escolherBucket((ate - desde) / 1000) : bucket
  return useQueries({
    queries: codes.map((code) => ({
      queryKey: ['historyRange', code, efetivo, desde, ate],
      queryFn: () => historyApi.getHistoryRange(code, desde, ate, bucket),
      enabled: code !== '' && ate > desde,
    })),
  })
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/lib/api && npx tsc -b --noEmit`
Expected: PASS e tipos limpos. `mock.test.ts` pode exigir ajuste se afirmar a forma do `HistoryApi`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api frontend/src/lib/queries.ts frontend/src/lib/types.ts
git commit -m "feat(frontend): contrato getHistoryRange e hook useHistoriesRange"
```

---

### Task 3: Paleta categórica e option multi-série

**Files:**
- Modify: `frontend/src/index.css`
- Create: `frontend/src/lib/paletaSeries.ts`
- Create: `frontend/src/components/multiChartOption.ts`
- Create: `frontend/src/components/multiChartOption.test.ts`

**Interfaces:**
- Consumes: `HistoryRangeResponse` (Task 2).
- Produces:
  - `SerieAnalise = { sensorCode: string; nome: string; unidade: string; cor: string; dados: HistoryRangeResponse | undefined }`
  - `buildMultiChartOption(series: SerieAnalise[], opcoes: { mostrarFaixa: boolean }): EChartsOption`
  - `usePaletaSeries(): string[]` — seis cores resolvidas do tema corrente

**Antes de escrever o CSS, carregue a skill `dataviz`.** A paleta é categórica e precisa funcionar nos dois temas sem colidir com os tokens semânticos.

- [ ] **Step 1: Write the failing test**

Criar `frontend/src/components/multiChartOption.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { buildMultiChartOption, type SerieAnalise } from './multiChartOption'
import type { HistoryRangeResponse } from '../lib/types'

function resposta(sensor: string, pontos: number[][]): HistoryRangeResponse {
  return {
    sensor_code: sensor, desde: '2026-03-10T00:00:00Z', ate: '2026-03-10T06:00:00Z',
    bucket: 'minuto', resolution: 'agg',
    points: pontos.map(([ts, min, max, avg]) => ({ ts, min, max, avg, count: 6 })),
  }
}

const TEMP: SerieAnalise = {
  sensorCode: 'T1', nome: 'Temp Expurgo', unidade: 'C', cor: '#111111',
  dados: resposta('T1', [[1000, 19, 21, 20], [2000, 20, 22, 21]]),
}
const PRESS: SerieAnalise = {
  sensorCode: 'P1', nome: 'Pressão Expurgo', unidade: 'Pa', cor: '#222222',
  dados: resposta('P1', [[1000, -12, -10, -11], [2000, -11, -9, -10]]),
}

describe('buildMultiChartOption', () => {
  it('uma unidade -> um eixo Y', () => {
    const o = buildMultiChartOption([TEMP], { mostrarFaixa: false })
    expect(Array.isArray(o.yAxis) ? o.yAxis : [o.yAxis]).toHaveLength(1)
  })

  it('duas unidades -> dois eixos, cada série no seu', () => {
    const o = buildMultiChartOption([TEMP, PRESS], { mostrarFaixa: false })
    const eixos = o.yAxis as { name?: string }[]
    expect(eixos).toHaveLength(2)
    expect(eixos[0].name).toBe('C')
    expect(eixos[1].name).toBe('Pa')
    const series = o.series as { name?: string; yAxisIndex?: number }[]
    expect(series.find((s) => s.name === 'Temp Expurgo')?.yAxisIndex).toBe(0)
    expect(series.find((s) => s.name === 'Pressão Expurgo')?.yAxisIndex).toBe(1)
  })

  it('plota o avg quando a resolução é agregada', () => {
    const o = buildMultiChartOption([TEMP], { mostrarFaixa: false })
    const serie = (o.series as { data?: number[][] }[])[0]
    expect(serie.data).toEqual([[1000, 20], [2000, 21]])
  })

  it('sem faixa, uma série por sensor', () => {
    const o = buildMultiChartOption([TEMP, PRESS], { mostrarFaixa: false })
    expect((o.series as unknown[]).length).toBe(2)
  })

  it('com faixa, acrescenta duas séries auxiliares empilhadas por sensor', () => {
    // Banda mín–máx no ECharts: uma linha invisível no mínimo + a diferença
    // empilhada com areaStyle. Sem o stack a área desceria até o zero.
    const o = buildMultiChartOption([TEMP], { mostrarFaixa: true })
    const series = o.series as { stack?: string; data?: number[][] }[]
    expect(series).toHaveLength(3)
    const base = series.find((s) => s.stack && s.data?.[0][1] === 19)
    const delta = series.find((s) => s.stack && s.data?.[0][1] === 2)
    expect(base).toBeDefined()
    expect(delta).toBeDefined()
    expect(base!.stack).toBe(delta!.stack)
  })

  it('não liga buracos: connectNulls falso em toda série de dado', () => {
    const o = buildMultiChartOption([TEMP, PRESS], { mostrarFaixa: false })
    for (const s of o.series as { connectNulls?: boolean }[]) {
      expect(s.connectNulls).toBe(false)
    }
  })

  it('série sem dado não quebra as outras', () => {
    const vazia: SerieAnalise = { ...PRESS, dados: undefined }
    const o = buildMultiChartOption([TEMP, vazia], { mostrarFaixa: false })
    expect((o.series as { data?: unknown[] }[]).some((s) => s.data?.length === 2)).toBe(true)
  })

  it('resolução raw plota value', () => {
    const raw: SerieAnalise = {
      ...TEMP,
      dados: { ...TEMP.dados!, resolution: 'raw', points: [{ ts: 1000, value: 42 }] },
    }
    const o = buildMultiChartOption([raw], { mostrarFaixa: false })
    expect((o.series as { data?: number[][] }[])[0].data).toEqual([[1000, 42]])
  })

  it('inclui dataZoom para navegação no tempo', () => {
    const o = buildMultiChartOption([TEMP], { mostrarFaixa: false })
    expect(o.dataZoom).toBeDefined()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/components/multiChartOption.test.ts`
Expected: FAIL — `Failed to resolve import "./multiChartOption"`

- [ ] **Step 3: Write minimal implementation**

Acrescentar a `frontend/src/index.css`, no bloco de tema claro:

```css
  /* Paleta categórica das séries de análise. Não reusa os tokens semânticos:
     uma série pintada de --color-crit lê como alarme. Seis cores distinguíveis
     entre si e legíveis sobre --color-surface. */
  --color-serie-1: #0b6fb4;
  --color-serie-2: #b8560f;
  --color-serie-3: #6b3fa0;
  --color-serie-4: #0f7a6c;
  --color-serie-5: #a12d6b;
  --color-serie-6: #5a6b1f;
```

E no bloco de tema escuro, as mesmas seis com luminosidade elevada para o fundo escuro:

```css
  --color-serie-1: #4aa8e8;
  --color-serie-2: #f0913f;
  --color-serie-3: #a684e0;
  --color-serie-4: #3fc0ac;
  --color-serie-5: #e878ac;
  --color-serie-6: #a8bd52;
```

Criar `frontend/src/lib/paletaSeries.ts`:

```ts
import { useThemeColor } from './useThemeColor'

// ECharts pinta em canvas e não resolve var(--...) — as cores precisam vir
// resolvidas, e reresolvidas quando o tema muda (mesma razão do critColor em
// TimeSeriesChart).
export function usePaletaSeries(): string[] {
  return [
    useThemeColor('--color-serie-1'),
    useThemeColor('--color-serie-2'),
    useThemeColor('--color-serie-3'),
    useThemeColor('--color-serie-4'),
    useThemeColor('--color-serie-5'),
    useThemeColor('--color-serie-6'),
  ]
}
```

Criar `frontend/src/components/multiChartOption.ts`:

```ts
import type { EChartsOption } from 'echarts'
import type { HistoryRangeResponse } from '../lib/types'

export type SerieAnalise = {
  sensorCode: string
  nome: string
  unidade: string
  cor: string
  dados: HistoryRangeResponse | undefined
}

type Ponto = [number, number]

function pontosDaLinha(dados: HistoryRangeResponse | undefined): Ponto[] {
  if (!dados) return []
  return dados.points.map((p) => [p.ts, 'value' in p ? p.value : p.avg])
}

// Banda mín–máx: ECharts não tem série de faixa. O truque padrão é uma linha
// invisível no mínimo mais a DIFERENÇA empilhada por cima com areaStyle — sem
// o stack, a área desceria até o zero do eixo.
function pontosDaBanda(dados: HistoryRangeResponse | undefined): { base: Ponto[]; delta: Ponto[] } {
  if (!dados || dados.resolution === 'raw') return { base: [], delta: [] }
  const base: Ponto[] = []
  const delta: Ponto[] = []
  for (const p of dados.points) {
    if (!('min' in p)) continue
    base.push([p.ts, p.min])
    delta.push([p.ts, p.max - p.min])
  }
  return { base, delta }
}

export function buildMultiChartOption(
  series: SerieAnalise[],
  opcoes: { mostrarFaixa: boolean },
): EChartsOption {
  // Ordem de aparição define qual unidade fica em cada eixo. A regra de no
  // máximo duas é imposta na seleção (AnalisePage); aqui, o excedente é
  // ignorado em vez de virar um terceiro eixo silencioso.
  const unidades: string[] = []
  for (const s of series) {
    if (!unidades.includes(s.unidade) && unidades.length < 2) unidades.push(s.unidade)
  }

  const yAxis = unidades.map((unidade, i) => ({
    type: 'value' as const,
    name: unidade,
    position: (i === 0 ? 'left' : 'right') as 'left' | 'right',
    scale: true,
  }))

  const desenhadas: Record<string, unknown>[] = []
  for (const s of series) {
    const eixo = unidades.indexOf(s.unidade)
    if (eixo < 0) continue

    if (opcoes.mostrarFaixa) {
      const { base, delta } = pontosDaBanda(s.dados)
      if (base.length) {
        const pilha = `faixa-${s.sensorCode}`
        desenhadas.push({
          name: `${s.nome} (mín)`, type: 'line', stack: pilha, yAxisIndex: eixo,
          data: base, symbol: 'none', connectNulls: false,
          lineStyle: { opacity: 0 }, silent: true,
          tooltip: { show: false }, legendHoverLink: false,
        })
        desenhadas.push({
          name: `${s.nome} (faixa)`, type: 'line', stack: pilha, yAxisIndex: eixo,
          data: delta, symbol: 'none', connectNulls: false,
          lineStyle: { opacity: 0 }, silent: true,
          areaStyle: { color: s.cor, opacity: 0.15 },
          tooltip: { show: false }, legendHoverLink: false,
        })
      }
    }

    desenhadas.push({
      name: s.nome, type: 'line', yAxisIndex: eixo,
      data: pontosDaLinha(s.dados), symbol: 'none',
      // Bucket sem dado é buraco, não reta ligando os dois lados como se
      // houvesse medição.
      connectNulls: false,
      lineStyle: { color: s.cor, width: 2 },
      itemStyle: { color: s.cor },
      sampling: 'lttb',
    })
  }

  return {
    grid: { left: 56, right: unidades.length > 1 ? 56 : 16, top: 36, bottom: 64 },
    legend: { data: series.map((s) => s.nome), top: 0 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'time' },
    yAxis,
    dataZoom: [
      { type: 'inside', throttle: 100 },
      { type: 'slider', height: 20, bottom: 8 },
    ],
    series: desenhadas as EChartsOption['series'],
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/components/multiChartOption.test.ts`
Expected: PASS (9 testes)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/index.css frontend/src/lib/paletaSeries.ts \
        frontend/src/components/multiChartOption.ts frontend/src/components/multiChartOption.test.ts
git commit -m "feat(frontend): option multi-serie com eixo duplo e faixa min-max"
```

---

### Task 4: `MultiSeriesChart`

**Files:**
- Create: `frontend/src/components/MultiSeriesChart.tsx`
- Create: `frontend/src/components/MultiSeriesChart.test.tsx`

**Interfaces:**
- Consumes: `buildMultiChartOption`, `SerieAnalise` (Task 3); `useECharts` (existente).
- Produces:
  ```tsx
  <MultiSeriesChart
    series={SerieAnalise[]}
    mostrarFaixa={boolean}
    status={'loading' | 'error' | undefined}
    onZoom={(desde: number, ate: number) => void}
  />
  ```

- [ ] **Step 1: Write the failing test**

Criar `frontend/src/components/MultiSeriesChart.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

const setOption = vi.fn()
vi.mock('echarts', () => ({
  init: () => ({ setOption, dispose: vi.fn(), resize: vi.fn(), on: vi.fn(), off: vi.fn() }),
}))

import { MultiSeriesChart } from './MultiSeriesChart'

describe('MultiSeriesChart', () => {
  it('mostra instrução quando não há série selecionada', () => {
    render(<MultiSeriesChart series={[]} mostrarFaixa={false} onZoom={() => {}} />)
    expect(screen.getByText(/selecione ao menos um sensor/i)).toBeInTheDocument()
  })

  it('mostra carregando enquanto busca', () => {
    render(
      <MultiSeriesChart
        series={[{ sensorCode: 'T1', nome: 'T', unidade: 'C', cor: '#000', dados: undefined }]}
        mostrarFaixa={false} status="loading" onZoom={() => {}} />,
    )
    expect(screen.getByText(/carregando/i)).toBeInTheDocument()
  })

  it('mostra falha quando a busca deu erro', () => {
    render(
      <MultiSeriesChart
        series={[{ sensorCode: 'T1', nome: 'T', unidade: 'C', cor: '#000', dados: undefined }]}
        mostrarFaixa={false} status="error" onZoom={() => {}} />,
    )
    expect(screen.getByText(/falha ao carregar/i)).toBeInTheDocument()
  })

  it('repassa a option para o ECharts quando há dado', () => {
    setOption.mockClear()
    render(
      <MultiSeriesChart
        series={[{
          sensorCode: 'T1', nome: 'T', unidade: 'C', cor: '#000',
          dados: {
            sensor_code: 'T1', desde: '2026-03-10T00:00:00Z', ate: '2026-03-10T01:00:00Z',
            bucket: 'raw', resolution: 'raw', points: [{ ts: 1000, value: 20 }],
          },
        }]}
        mostrarFaixa={false} onZoom={() => {}} />,
    )
    expect(setOption).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/components/MultiSeriesChart.test.tsx`
Expected: FAIL — `Failed to resolve import "./MultiSeriesChart"`

- [ ] **Step 3: Write minimal implementation**

Criar `frontend/src/components/MultiSeriesChart.tsx`:

```tsx
import { useEffect } from 'react'
import { useECharts } from './useECharts'
import { buildMultiChartOption, type SerieAnalise } from './multiChartOption'

// Irmão do TimeSeriesChart, não uma generalização dele: aquele carrega
// markArea de fora-limite, gaps offline, faixa de silêncio e merge da cauda ao
// vivo, tudo escrito para UMA série. Aqui não há cauda ao vivo (decisão de
// escopo) e a leitura é comparativa, não de vigilância.
export function MultiSeriesChart({
  series, mostrarFaixa, status, onZoom,
}: {
  series: SerieAnalise[]
  mostrarFaixa: boolean
  status?: 'loading' | 'error'
  onZoom: (desde: number, ate: number) => void
}) {
  const { el, chart } = useECharts()

  useEffect(() => {
    chart.current?.setOption(buildMultiChartOption(series, { mostrarFaixa }), { notMerge: true })
  }, [series, mostrarFaixa, chart])

  useEffect(() => {
    const instancia = chart.current
    if (!instancia) return
    // O evento traz startValue/endValue quando o eixo é `time`; é o intervalo
    // visível em ms, que é exatamente o que a página precisa para rebuscar.
    const aoZoom = (evento: unknown) => {
      const e = evento as { batch?: { startValue?: number; endValue?: number }[]
                            startValue?: number; endValue?: number }
      const alvo = e.batch?.[0] ?? e
      if (typeof alvo.startValue === 'number' && typeof alvo.endValue === 'number') {
        onZoom(alvo.startValue, alvo.endValue)
      }
    }
    instancia.on('datazoom', aoZoom)
    return () => { instancia.off('datazoom', aoZoom) }
  }, [chart, onZoom])

  const temDado = series.some((s) => (s.dados?.points.length ?? 0) > 0)
  const mensagem = series.length === 0
    ? 'Selecione ao menos um sensor da área'
    : temDado
      ? null
      : status === 'loading'
        ? 'Carregando…'
        : status === 'error'
          ? 'Falha ao carregar o histórico'
          : 'Sem dados no período'

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', minHeight: 320 }}>
      <div ref={el} style={{ width: '100%', height: '100%' }} />
      {mensagem && (
        <div
          className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm font-medium"
          style={{ color: 'var(--color-muted)' }}
        >
          {mensagem}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/components/MultiSeriesChart.test.tsx`
Expected: PASS (4 testes)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/MultiSeriesChart.tsx frontend/src/components/MultiSeriesChart.test.tsx
git commit -m "feat(frontend): MultiSeriesChart com zoom emitido para o container"
```

---

### Task 5: `AnalisePage` — seleção, regra das unidades e estado na URL

**Files:**
- Create: `frontend/src/pages/AnalisePage.tsx`
- Create: `frontend/src/pages/AnalisePage.test.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `AreaSelect`, `SearchSelect` + `sensorConfig`, `useSensors`, `useHistoriesRange` (Task 2), `MultiSeriesChart` (Task 4), `usePaletaSeries` (Task 3), `escolherBucket` (Task 1).
- Produces: rota `/analise` com estado em query string:
  `?area=<code>&sensores=<a,b>&desde=<ms>&ate=<ms>&bucket=<auto|raw|…>`

Intervalo default ao abrir sem parâmetros: últimas 24 h.

- [ ] **Step 1: Write the failing test**

Criar `frontend/src/pages/AnalisePage.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'

vi.mock('echarts', () => ({
  init: () => ({ setOption: vi.fn(), dispose: vi.fn(), resize: vi.fn(), on: vi.fn(), off: vi.fn() }),
}))

import { AnalisePage } from './AnalisePage'
import { metaApi, historyApi } from '../lib/api'

const SENSORES = [
  { sensor_code: 'T1', name: 'Temp A', unidade: 'C', protocolo_origem: '4-20ma',
    measurement_type: { code: 'temperatura', name: 'Temperatura' },
    area: { area_code: 'AREA-X', name: 'Expurgo', category: 'EXPURGO' } },
  { sensor_code: 'P1', name: 'Pressão A', unidade: 'Pa', protocolo_origem: '4-20ma',
    measurement_type: { code: 'pressao', name: 'Pressão' },
    area: { area_code: 'AREA-X', name: 'Expurgo', category: 'EXPURGO' } },
  { sensor_code: 'U1', name: 'Umidade A', unidade: '%UR', protocolo_origem: '4-20ma',
    measurement_type: { code: 'umidade', name: 'Umidade' },
    area: { area_code: 'AREA-X', name: 'Expurgo', category: 'EXPURGO' } },
  { sensor_code: 'T9', name: 'Temp Outra', unidade: 'C', protocolo_origem: '4-20ma',
    measurement_type: { code: 'temperatura', name: 'Temperatura' },
    area: { area_code: 'AREA-Y', name: 'Preparo', category: 'PREPARO' } },
]

let ultimaUrl = ''
function EspiaUrl() {
  ultimaUrl = useLocation().search
  return null
}

function renderizar(entrada = '/analise') {
  vi.spyOn(metaApi, 'listSensors').mockResolvedValue(SENSORES as never)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entrada]}>
        <Routes>
          <Route path="/analise" element={<><AnalisePage /><EspiaUrl /></>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AnalisePage', () => {
  it('só oferece sensores da área escolhida', async () => {
    renderizar('/analise?area=AREA-X')
    await waitFor(() => expect(screen.getByText('Temp A')).toBeInTheDocument())
    expect(screen.queryByText('Temp Outra')).not.toBeInTheDocument()
  })

  it('bloqueia a terceira unidade com aviso', async () => {
    const usuario = userEvent.setup()
    renderizar('/analise?area=AREA-X&sensores=T1,P1')
    await waitFor(() => expect(screen.getByText('Umidade A')).toBeInTheDocument())
    await usuario.click(screen.getByText('Umidade A'))
    expect(await screen.findByText(/duas unidades/i)).toBeInTheDocument()
    // E o sensor não entrou na seleção.
    expect(ultimaUrl).not.toContain('U1')
  })

  it('trocar de área limpa a seleção de sensores', async () => {
    const usuario = userEvent.setup()
    renderizar('/analise?area=AREA-X&sensores=T1')
    await waitFor(() => expect(screen.getByText('Temp A')).toBeInTheDocument())
    await usuario.click(screen.getByRole('button', { name: /área/i }))
    await usuario.click(await screen.findByText('Preparo'))
    await waitFor(() => expect(ultimaUrl).not.toContain('T1'))
  })

  it('espelha a seleção na URL', async () => {
    const usuario = userEvent.setup()
    renderizar('/analise?area=AREA-X')
    await waitFor(() => expect(screen.getByText('Temp A')).toBeInTheDocument())
    await usuario.click(screen.getByText('Temp A'))
    await waitFor(() => expect(ultimaUrl).toContain('sensores=T1'))
  })

  it('sem sensor selecionado não busca histórico', async () => {
    const espia = vi.spyOn(historyApi, 'getHistoryRange')
    renderizar('/analise?area=AREA-X')
    await waitFor(() => expect(screen.getByText('Temp A')).toBeInTheDocument())
    expect(espia).not.toHaveBeenCalled()
  })

  it('busca com o intervalo e o bucket da URL', async () => {
    const espia = vi.spyOn(historyApi, 'getHistoryRange')
    const desde = Date.UTC(2026, 2, 10, 0, 0)
    const ate = Date.UTC(2026, 2, 10, 6, 0)
    renderizar(`/analise?area=AREA-X&sensores=T1&desde=${desde}&ate=${ate}&bucket=hora`)
    await waitFor(() => expect(espia).toHaveBeenCalledWith('T1', desde, ate, 'hora'))
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/pages/AnalisePage.test.tsx`
Expected: FAIL — `Failed to resolve import "./AnalisePage"`

- [ ] **Step 3: Write minimal implementation**

Criar `frontend/src/pages/AnalisePage.tsx` com esta estrutura:

```tsx
import { useCallback, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { useSensors, useHistoriesRange } from '../lib/queries'
import { AreaSelect } from '../components/select/AreaSelect'
import { SearchSelect } from '../components/select/SearchSelect'
import { sensorConfig } from '../components/select/entityConfigs'
import { MultiSeriesChart } from '../components/MultiSeriesChart'
import { usePaletaSeries } from '../lib/paletaSeries'
import type { SerieAnalise } from '../components/multiChartOption'
import type { BucketPedido, SensorMeta } from '../lib/types'

const DIA_MS = 86_400_000
const BUCKETS: BucketPedido[] = ['auto', 'minuto', 'hora', 'dia', 'semana', 'mes']

export function AnalisePage() {
  const [params, setParams] = useSearchParams()
  const [aviso, setAviso] = useState<string | null>(null)

  const area = params.get('area') ?? ''
  const selecionados = (params.get('sensores') ?? '').split(',').filter(Boolean)
  const bucket = (params.get('bucket') ?? 'auto') as BucketPedido
  // Default de intervalo: últimas 24 h. Calculado uma vez por render a partir
  // da URL; o zoom passa a mandar valores explícitos.
  const ate = Number(params.get('ate')) || Date.now()
  const desde = Number(params.get('desde')) || ate - DIA_MS

  const sensores = useSensors().data ?? []
  const daArea = useMemo(
    () => sensores.filter((s) => s.area.area_code === area),
    [sensores, area],
  )

  const unidadesAtivas = useMemo(() => {
    const u: string[] = []
    for (const code of selecionados) {
      const s = daArea.find((x) => x.sensor_code === code)
      if (s && !u.includes(s.unidade)) u.push(s.unidade)
    }
    return u
  }, [selecionados, daArea])

  const atualizar = useCallback((mudancas: Record<string, string | null>) => {
    const proximo = new URLSearchParams(params)
    for (const [chave, valor] of Object.entries(mudancas)) {
      if (valor === null || valor === '') proximo.delete(chave)
      else proximo.set(chave, valor)
    }
    setParams(proximo, { replace: true })
  }, [params, setParams])

  // Regra das duas unidades: bloqueio na ENTRADA. Deixar selecionar e falhar
  // depois seria pior — o usuário já teria montado a comparação errada.
  const aoMudarSensores = (codes: string[]) => {
    const novos = codes.filter((c) => !selecionados.includes(c))
    for (const code of novos) {
      const s = daArea.find((x) => x.sensor_code === code)
      if (s && !unidadesAtivas.includes(s.unidade) && unidadesAtivas.length >= 2) {
        setAviso(
          `O gráfico comporta duas unidades — hoje ${unidadesAtivas.join(' e ')}. ` +
          `Remova um sensor para incluir ${s.unidade}.`,
        )
        return
      }
    }
    setAviso(null)
    atualizar({ sensores: codes.join(',') })
  }

  const aoMudarArea = (novaArea: string | null) => {
    setAviso(null)
    atualizar({ area: novaArea, sensores: null })
  }

  const aoZoom = useCallback((novoDesde: number, novoAte: number) => {
    atualizar({ desde: String(Math.round(novoDesde)), ate: String(Math.round(novoAte)) })
  }, [atualizar])

  const resultados = useHistoriesRange(selecionados, desde, ate, bucket)
  const paleta = usePaletaSeries()
  const [faixaManual, setFaixaManual] = useState<boolean | null>(null)
  const mostrarFaixa = faixaManual ?? selecionados.length <= 2

  const series: SerieAnalise[] = selecionados.map((code, i) => {
    const meta = daArea.find((s) => s.sensor_code === code)
    return {
      sensorCode: code,
      nome: meta?.name ?? code,
      unidade: meta?.unidade ?? '',
      cor: paleta[i % paleta.length],
      dados: resultados[i]?.data,
    }
  })

  const status = resultados.some((r) => r.isError)
    ? ('error' as const)
    : resultados.some((r) => r.isLoading)
      ? ('loading' as const)
      : undefined

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <div className="flex flex-wrap items-end gap-4">
        <AreaSelect label="Área" value={area || null} onChange={aoMudarArea} />
        <SearchSelect
          items={daArea}
          config={sensorConfig}
          multiple
          label="Sensores"
          value={selecionados}
          onChange={aoMudarSensores}
        />
        <div className="inline-flex gap-1 rounded-lg p-1"
             style={{ background: 'var(--color-panel)', border: '1px solid var(--color-line)' }}
             role="group" aria-label="Resolução">
          {BUCKETS.map((b) => (
            <button key={b} type="button" aria-pressed={b === bucket}
                    onClick={() => atualizar({ bucket: b })}
                    className="min-h-11 rounded-md px-3 py-2 text-sm font-semibold">
              {b}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={mostrarFaixa}
                 onChange={(e) => setFaixaManual(e.target.checked)} />
          Faixa mín–máx
        </label>
      </div>

      {aviso && (
        <div role="status" className="rounded-lg px-4 py-2 text-sm"
             style={{ background: 'var(--color-warn-soft)', color: 'var(--color-ink)' }}>
          {aviso}
        </div>
      )}

      <div className="min-h-0 flex-1 rounded-lg p-3"
           style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}>
        <MultiSeriesChart series={series} mostrarFaixa={mostrarFaixa}
                          status={status} onZoom={aoZoom} />
      </div>
    </div>
  )
}
```

O estilo dos botões de bucket segue o `WindowSelector` (chip ativo com
`--color-primary` de fundo e `--color-surface` no texto, contraste já verificado
nos dois temas nesse componente) — copiar de lá em vez de reinventar.

Registrar a rota em `frontend/src/App.tsx`, dentro do `<Route element={<AuthGuard />}>`:

```tsx
<Route path="/analise" element={<AnalisePage />} />
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/pages/AnalisePage.test.tsx && npx tsc -b --noEmit`
Expected: PASS (6 testes) e tipos limpos.

Se algum seletor do teste não casar com o markup escolhido (por exemplo o
`getByRole('button', { name: /área/i })`), ajuste **o teste** para o markup real
— desde que continue provando o mesmo comportamento.

- [ ] **Step 5: Run the whole suite**

Run: `npx vitest run`
Expected: PASS. Atenção especial a `App.test.tsx` e `TimeSeriesChart.test.tsx` — este último não pode ter mudado.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/AnalisePage.tsx frontend/src/pages/AnalisePage.test.tsx frontend/src/App.tsx
git commit -m "feat(frontend): pagina /analise com selecao por area e estado na URL"
```

---

### Task 6: Zoom com debounce

O zoom do ECharts dispara `datazoom` a cada quadro. Sem amortecer, arrastar a barra vira dezenas de buscas.

**Files:**
- Create: `frontend/src/lib/useDebouncedCallback.ts`
- Create: `frontend/src/lib/useDebouncedCallback.test.ts`
- Modify: `frontend/src/pages/AnalisePage.tsx`
- Modify: `frontend/src/pages/AnalisePage.test.tsx`

**Interfaces:**
- Produces: `useDebouncedCallback<T extends unknown[]>(fn: (...args: T) => void, atrasoMs: number): (...args: T) => void`

- [ ] **Step 1: Write the failing test**

Criar `frontend/src/lib/useDebouncedCallback.test.ts`:

```ts
import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useDebouncedCallback } from './useDebouncedCallback'

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers() })

describe('useDebouncedCallback', () => {
  it('chama uma vez só, com o último argumento', () => {
    const alvo = vi.fn()
    const { result } = renderHook(() => useDebouncedCallback(alvo, 300))
    act(() => { result.current(1); result.current(2); result.current(3) })
    expect(alvo).not.toHaveBeenCalled()
    act(() => { vi.advanceTimersByTime(300) })
    expect(alvo).toHaveBeenCalledTimes(1)
    expect(alvo).toHaveBeenCalledWith(3)
  })

  it('cancela o pendente ao desmontar', () => {
    const alvo = vi.fn()
    const { result, unmount } = renderHook(() => useDebouncedCallback(alvo, 300))
    act(() => { result.current(1) })
    unmount()
    act(() => { vi.advanceTimersByTime(300) })
    expect(alvo).not.toHaveBeenCalled()
  })
})
```

Acrescentar a `frontend/src/pages/AnalisePage.test.tsx`. O mock do ECharts no
topo do arquivo passa a guardar o handler de `datazoom`, para o teste poder
disparar o gesto sem canvas:

```tsx
// Substituir o mock do topo do arquivo por este, que captura o handler:
const handlers: Record<string, (e: unknown) => void> = {}
vi.mock('echarts', () => ({
  init: () => ({
    setOption: vi.fn(), dispose: vi.fn(), resize: vi.fn(),
    on: (evento: string, cb: (e: unknown) => void) => { handlers[evento] = cb },
    off: () => {},
  }),
}))
```

```tsx
  it('zoom só atualiza a URL depois do debounce', async () => {
    vi.useFakeTimers()
    try {
      renderizar('/analise?area=AREA-X&sensores=T1')
      await vi.waitFor(() => expect(handlers.datazoom).toBeDefined())
      const urlAntes = ultimaUrl

      // Três eventos em sequência, como o gesto real dispara.
      act(() => {
        handlers.datazoom({ startValue: 1_000_000, endValue: 2_000_000 })
        handlers.datazoom({ startValue: 1_100_000, endValue: 2_100_000 })
        handlers.datazoom({ startValue: 1_200_000, endValue: 2_200_000 })
      })
      expect(ultimaUrl).toBe(urlAntes)

      act(() => { vi.advanceTimersByTime(300) })
      // Só o último gesto vira estado.
      expect(ultimaUrl).toContain('desde=1200000')
      expect(ultimaUrl).toContain('ate=2200000')
    } finally {
      vi.useRealTimers()
    }
  })
```

Importar `act` de `@testing-library/react` no topo do arquivo de teste.

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/lib/useDebouncedCallback.test.ts`
Expected: FAIL — módulo não existe

- [ ] **Step 3: Write minimal implementation**

Criar `frontend/src/lib/useDebouncedCallback.ts`:

```ts
import { useCallback, useEffect, useRef } from 'react'

// O evento `datazoom` do ECharts dispara a cada quadro do gesto. Sem amortecer,
// arrastar a barra vira dezenas de buscas; o TanStack cancela as anteriores,
// mas o servidor já teria recebido todas.
export function useDebouncedCallback<T extends unknown[]>(
  fn: (...args: T) => void,
  atrasoMs: number,
) {
  const alvo = useRef(fn)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => { alvo.current = fn }, [fn])
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current) }, [])

  return useCallback((...args: T) => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => { alvo.current(...args) }, atrasoMs)
  }, [atrasoMs])
}
```

Em `AnalisePage.tsx`, envolver o `aoZoom`:

```tsx
  const aoZoomAmortecido = useDebouncedCallback(aoZoom, 300)
```

e passar `onZoom={aoZoomAmortecido}` ao `MultiSeriesChart`.

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/lib/useDebouncedCallback.test.ts src/pages/AnalisePage.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/useDebouncedCallback.ts frontend/src/lib/useDebouncedCallback.test.ts \
        frontend/src/pages/AnalisePage.tsx frontend/src/pages/AnalisePage.test.tsx
git commit -m "feat(frontend): amortecer o zoom antes de rebuscar o historico"
```

---

### Task 7: Entradas para a página

**Files:**
- Modify: `frontend/src/components/Topbar.tsx`
- Modify: `frontend/src/components/Topbar.test.tsx`
- Modify: `frontend/src/components/SensorDetailDrawer.tsx`
- Modify: `frontend/src/components/SensorDetailDrawer.test.tsx`

**Interfaces:**
- Consumes: rota `/analise` (Task 5).
- Produces: link na Topbar e botão no drawer, este último levando à página já com área e sensor preenchidos.

- [ ] **Step 1: Write the failing test**

Acrescentar a `frontend/src/components/Topbar.test.tsx`:

```tsx
  it('oferece link para a página de análise', () => {
    // (usar o mesmo wrapper de render já existente neste arquivo)
    expect(screen.getByRole('link', { name: /análise/i })).toHaveAttribute('href', '/analise')
  })
```

Acrescentar a `frontend/src/components/SensorDetailDrawer.test.tsx`:

```tsx
  it('leva à análise com a área e o sensor preenchidos', () => {
    // (renderizar o drawer com um sensor cuja área é AREA-X, como já faz o
    // arquivo; ajustar os códigos aos fixtures locais)
    const link = screen.getByRole('link', { name: /analisar histórico/i })
    expect(link.getAttribute('href')).toContain('area=AREA-X')
    expect(link.getAttribute('href')).toContain('sensores=')
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/components/Topbar.test.tsx src/components/SensorDetailDrawer.test.tsx`
Expected: FAIL — nenhum dos dois links existe

- [ ] **Step 3: Write minimal implementation**

Na `Topbar`, depois do chip da unidade, um `<Link to="/analise">Análise</Link>` do
`react-router`, no mesmo vocabulário visual dos demais controles do cabeçalho
(altura mínima 44 px, `focus-visible` com `--color-primary`, cor `--color-muted`
que vira `--color-ink` no hover).

A `Topbar` hoje é puramente apresentacional e não usa router. Se o `Link`
quebrar algum teste que a renderiza fora de um `MemoryRouter`, envolver esses
testes no router é a correção — não trocar o `Link` por `<a href>`, que perderia
a navegação client-side.

No `SensorDetailDrawer`, um link para
`/analise?area=${sensor.area.area_code}&sensores=${sensor.sensor_code}`
com o rótulo *Analisar histórico*.

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run`
Expected: PASS na suíte inteira.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Topbar.tsx frontend/src/components/Topbar.test.tsx \
        frontend/src/components/SensorDetailDrawer.tsx frontend/src/components/SensorDetailDrawer.test.tsx
git commit -m "feat(frontend): entradas para a analise na topbar e no drawer"
```

---

### Task 8: Verificação no browser contra a stack real

Os testes rodam em jsdom com o ECharts mockado — nenhum deles prova que o gráfico **desenha**. Esta task é a que prova.

**Files:**
- Nenhum arquivo de código permanente. Produz capturas e um commit de registro.

- [ ] **Step 1: Subir o frontend contra a api real**

```bash
cd frontend
VITE_API_MODE=real npm run dev
```

Confirmar que a api está de pé (`curl -s localhost:8000/docs -o /dev/null -w '%{http_code}\n'` → 200) e que a migração do Plano A foi aplicada.

- [ ] **Step 2: Abrir a página com dois sensores de unidades diferentes**

Usar Playwright — `chrome-devtools-mcp` não sobe neste ambiente (WSL2). Adaptar
`frontend/e2e/shot.spec.ts` para navegar até
`/analise?area=AREA-EXPURGO&sensores=SNR-E2E-CH1,PD-HUB-CH2` e capturar a tela.

Conferir na captura:

1. Duas linhas com cores distintas, nenhuma delas vermelha de alarme.
2. Eixo Y esquerdo com a unidade do primeiro sensor, direito com a do segundo.
3. Faixa mín–máx translúcida na cor de cada série.
4. A série alcança o instante atual — sem o degrau vazio à direita que a
   materialização causava antes do Plano A.

- [ ] **Step 3: Exercitar o zoom**

Dar zoom até uma janela de ~1 h e conferir na aba de rede que a busca refez com
`bucket=raw` (ou `minuto`); dar zoom out até ~1 ano e conferir `dia`. Voltar ao
zoom anterior deve ser instantâneo, sem nova requisição — é a prova de que a
chave de cache por bucket está certa.

- [ ] **Step 4: Tentar a terceira unidade**

Selecionar um terceiro sensor de unidade diferente e confirmar que o aviso
aparece e que ele não entra no gráfico.

- [ ] **Step 5: Conferir os dois temas**

Alternar o tema pelo `ThemeToggle` e confirmar que as seis cores de série
continuam distinguíveis e legíveis sobre o fundo escuro.

- [ ] **Step 6: Registrar o resultado**

```bash
git commit --allow-empty -m "test: verificacao visual da pagina de analise

Duas unidades em eixos opostos, zoom trocando de bucket com cache por
degrau, terceira unidade bloqueada, paleta legivel nos dois temas."
```

---

## Self-Review

**Cobertura da spec (Parte B):**

| Requisito | Task |
|---|---|
| B.1 arquivos novos, `chartOption.ts` intacto | 3, 4 (constraint global, verificada na suíte da Task 5) |
| B.2 seleção por área | 5 |
| B.2 regra das duas unidades com aviso | 5 |
| B.2 troca de área limpa a seleção | 5 |
| B.3 zoom com debounce e bucket automático | 4 (evento), 6 (debounce) |
| B.3 cache por degrau | 2 (chave com bucket efetivo), 8 (prova no browser) |
| B.3 barra de degraus manual | 5 |
| B.4 linha do avg, faixa mín–máx, dois eixos, `connectNulls: false` | 3 |
| B.5 estado na URL | 5 |
| B.6 entradas Topbar e drawer | 7 |
| Sem cauda ao vivo | nenhuma task importa `useLiveTail` |
| Escada espelhada do contrato | 1 |

**Consistência de nomes:** `SerieAnalise` e `buildMultiChartOption` (Task 3) são consumidos com essas assinaturas nas Tasks 4 e 5. `getHistoryRange(code, desde, ate, bucket)` (Task 2) é chamado com essa ordem no teste da Task 5. `useHistoriesRange` devolve resultados na ordem de `codes`, o que a Task 5 assume ao casar `resultados[i]` com `selecionados[i]`.

**Onde este plano é deliberadamente menos prescritivo:** o markup do layout na Task 5 e os seletores dos testes das Tasks 5-7 dependem do markup escolhido. O comportamento a provar está fixado; a forma exata de alcançá-lo no teste pode ser ajustada, e isso está dito em cada passo onde vale.
