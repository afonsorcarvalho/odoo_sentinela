# Widgets: sinal offline + faixas fora-de-limite — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sinalizar sensor offline no KpiWidget e no gráfico temporal, e marcar no gráfico os períodos em que a série esteve fora do limite.

**Architecture:** Reuso da máquina de frescor existente (`freshness()`, `FreshnessBadge`, `useNow()`, padrão de `AreaCard`). Faixas fora-de-limite derivadas dos pontos plotados por uma função pura nova (`computeOutOfRangeBands`), irmã de `freshness()`. Nada de API nova. `now` sempre injetado (nunca `Date.now()` nas funções puras/`buildChartOption`).

**Tech Stack:** React 18, TypeScript, Vitest + Testing Library, ECharts 6 (via `useECharts`), TanStack Query.

## Global Constraints

- Rodar testes: `npm test` (roda `vitest run`) a partir de `frontend/`. Suite atual: 421 verdes.
- Funções puras e `buildChartOption` **nunca** chamam `Date.now()` — `now` entra por parâmetro. Mesma regra que `freshness()` (`lib/freshness.ts:18-25`).
- ECharts pinta em `<canvas>` e não resolve `var(--...)`: toda cor de tema que alimenta o chart passa por `useThemeColor` no componente e chega concreta a `buildChartOption` (`components/chartOption.ts:6-15`).
- Tokens de cor existentes: `--color-crit-soft` (faixa vermelha suave), `--color-muted` (faixa de silêncio), `--color-good-soft` (faixa verde já usada).
- `useLiveTail(code)` devolve `{ last, tail }` — `last` é o último `LivePoint` ou `null`.
- Thresholds de frescor: `DEFAULT_STALE_MS = 5min`, `DEFAULT_OFFLINE_MS = 15min` (`lib/freshness.ts:8-9`).

---

## File Structure

- `frontend/src/components/chartOption.ts` — nova fn pura `computeOutOfRangeBands` + render de faixas X e faixa de silêncio no `markArea`; nova assinatura de `buildChartOption`.
- `frontend/src/components/chartOption.test.ts` — testes da fn pura e do render.
- `frontend/src/components/TimeSeriesChart.tsx` — nova prop `now`, resolve `--color-crit-soft`/`--color-muted`, repassa a `buildChartOption`.
- `frontend/src/components/widgets/KpiWidget.tsx` — `useNow`, tier, badge, número atenuado.
- `frontend/src/components/widgets/KpiWidget.test.tsx` — testes de badge/atenuação.
- `frontend/src/components/widgets/TimeseriesWidget.tsx` — `useNow`, tier→badge, passa `now`.
- `frontend/src/components/widgets/TimeseriesWidget.test.tsx` — teste de badge por tier.

---

## Task 1: Função pura `computeOutOfRangeBands`

**Files:**
- Modify: `frontend/src/components/chartOption.ts`
- Test: `frontend/src/components/chartOption.test.ts`

**Interfaces:**
- Consumes: `Threshold` de `../lib/types` (`{ limite_min: number; limite_max: number }`).
- Produces:
  ```ts
  export type Banda = { inicio: number; fim: number; direcao: 'acima' | 'abaixo' }
  export function computeOutOfRangeBands(data: [number, number][], threshold: Threshold | null): Banda[]
  ```

Regras (do spec): compara o valor plotado (`data[i][1]`); run contíguo fora do limite = uma banda; troca de direção fecha e abre; ponto isolado estende ½ até o vizinho (sem vizinho: ½ do espaçamento mediano); gap entre pontos fora-limite consecutivos > 3× espaçamento mediano quebra a banda; `threshold` null → `[]`.

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao fim de `chartOption.test.ts` (antes ou depois do `describe` existente):

```ts
import { computeOutOfRangeBands } from './chartOption'

const th: Threshold = { sensor_id: 'S', limite_min: 18, limite_max: 22, is_valor_padrao_regulatorio: true }

describe('computeOutOfRangeBands', () => {
  it('run contiguo acima do limite vira uma banda com direcao acima', () => {
    // espacamento mediano = 100
    const data: [number, number][] = [[0, 20], [100, 25], [200, 26], [300, 20]]
    const bandas = computeOutOfRangeBands(data, th)
    expect(bandas).toHaveLength(1)
    expect(bandas[0].direcao).toBe('acima')
    // banda cobre [100,200] estendida 1/2 ate os vizinhos dentro (50 e 250)
    expect(bandas[0].inicio).toBe(50)
    expect(bandas[0].fim).toBe(250)
  })

  it('run abaixo do limite vira banda com direcao abaixo', () => {
    const data: [number, number][] = [[0, 20], [100, 10], [200, 20]]
    const bandas = computeOutOfRangeBands(data, th)
    expect(bandas).toHaveLength(1)
    expect(bandas[0].direcao).toBe('abaixo')
  })

  it('troca de direcao sem passar por dentro fecha e abre nova banda', () => {
    // 25 (acima) -> 10 (abaixo): dois pontos fora, direcoes distintas
    const data: [number, number][] = [[0, 20], [100, 25], [200, 10], [300, 20]]
    const bandas = computeOutOfRangeBands(data, th)
    expect(bandas).toHaveLength(2)
    expect(bandas[0].direcao).toBe('acima')
    expect(bandas[1].direcao).toBe('abaixo')
  })

  it('ponto isolado fora do limite gera banda de largura positiva', () => {
    const data: [number, number][] = [[0, 20], [100, 25], [200, 20]]
    const bandas = computeOutOfRangeBands(data, th)
    expect(bandas).toHaveLength(1)
    expect(bandas[0].fim).toBeGreaterThan(bandas[0].inicio)
  })

  it('gap > 3x o espacamento mediano quebra a banda em duas', () => {
    // espacamento mediano = 100; salto de 100->1000 (gap 900 > 300)
    const data: [number, number][] = [[0, 25], [100, 25], [1000, 25], [1100, 25]]
    const bandas = computeOutOfRangeBands(data, th)
    expect(bandas).toHaveLength(2)
  })

  it('serie toda dentro do limite devolve []', () => {
    const data: [number, number][] = [[0, 19], [100, 20], [200, 21]]
    expect(computeOutOfRangeBands(data, th)).toEqual([])
  })

  it('threshold null devolve []', () => {
    const data: [number, number][] = [[0, 100], [100, 200]]
    expect(computeOutOfRangeBands(data, null)).toEqual([])
  })

  it('data vazia devolve []', () => {
    expect(computeOutOfRangeBands([], th)).toEqual([])
  })
})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `npm test -- chartOption`
Expected: FAIL — `computeOutOfRangeBands is not a function` / não exportada.

- [ ] **Step 3: Implementar a função pura**

Adicionar em `chartOption.ts` (depois dos imports, antes de `buildChartOption`):

```ts
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
```

- [ ] **Step 4: Rodar e ver passar**

Run: `npm test -- chartOption`
Expected: PASS (os novos testes + os antigos de `buildChartOption`).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/chartOption.ts frontend/src/components/chartOption.test.ts
git commit -m "feat(chart): computeOutOfRangeBands deriva faixas fora-de-limite dos pontos plotados"
```

---

## Task 2: Render das faixas X e faixa de silêncio em `buildChartOption`

**Files:**
- Modify: `frontend/src/components/chartOption.ts:4-91` (assinatura + `markArea`)
- Test: `frontend/src/components/chartOption.test.ts`

**Interfaces:**
- Consumes: `computeOutOfRangeBands` (Task 1); `DEFAULT_STALE_MS` de `../lib/freshness`.
- Produces: nova assinatura
  ```ts
  buildChartOption(
    history, threshold,
    critColor = 'var(--color-crit)',
    goodSoftColor = 'var(--color-good-soft)',
    tail = [],
    now?: number,
    critSoftColor = 'var(--color-crit-soft)',
    mutedColor = 'var(--color-muted)',
  )
  ```
  Params novos vão no fim → chamadas posicionais existentes (`buildChartOption(hist, t)`, e a de `TimeSeriesChart`) continuam válidas.

`markArea.data` passa a conter, nesta ordem: [faixa verde em Y] → [faixas X vermelhas] → [faixa cinza de silêncio, se houver]. Cada item carrega o próprio `itemStyle` (agora que as cores diferem por item); o `itemStyle` do root do `markArea` é removido.

Faixa X: par `[{ xAxis: inicio, itemStyle, name: label }, { xAxis: fim }]`, cor `critSoftColor`. Label pré-formatado no `name` (ver spec): `` `${direcao} do limite` ``.

Faixa de silêncio: só se `now != null`, `data` não-vazia, e `now - ultimoTs > DEFAULT_STALE_MS`. Par `[{ xAxis: ultimoTs, itemStyle }, { xAxis: now }]`, cor `mutedColor`, opacity baixa.

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao `describe('buildChartOption', ...)`:

```ts
  it('desenha faixa X vermelha quando a serie sai do limite', () => {
    const h: HistoryResponse = {
      sensor_code: 'S', window: '1h', resolution: 'raw',
      points: [{ ts: 0, value: 20 }, { ts: 100, value: 25 }, { ts: 200, value: 20 }],
    }
    const opt = buildChartOption(h, t) as any
    const areas = opt.series[0].markArea.data as any[]
    // primeiro item e a faixa verde em Y (yAxis); deve haver ao menos um item X (xAxis)
    const xBands = areas.filter((pair) => 'xAxis' in pair[0])
    expect(xBands.length).toBeGreaterThanOrEqual(1)
    expect(xBands[0][0].name).toMatch(/acima do limite/)
  })

  it('faixa verde de conformidade continua presente (primeiro item, em Y)', () => {
    const opt = buildChartOption(hist, t) as any
    const areas = opt.series[0].markArea.data as any[]
    expect('yAxis' in areas[0][0]).toBe(true)
  })

  it('desenha faixa de silencio quando now esta muito alem do ultimo ponto', () => {
    const opt = buildChartOption(hist, t, undefined, undefined, [], 2000 + 6 * 60_000) as any
    const areas = opt.series[0].markArea.data as any[]
    const silencio = areas.filter((pair) => 'xAxis' in pair[0] && pair[1].xAxis === 2000 + 6 * 60_000)
    expect(silencio).toHaveLength(1)
  })

  it('nao desenha faixa de silencio quando now esta perto do ultimo ponto', () => {
    const opt = buildChartOption(hist, t, undefined, undefined, [], 2000 + 60_000) as any
    const areas = (opt.series[0].markArea?.data ?? []) as any[]
    const silencio = areas.filter((pair) => 'xAxis' in pair[0] && pair[1].xAxis === 2000 + 60_000)
    expect(silencio).toHaveLength(0)
  })
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `npm test -- chartOption`
Expected: FAIL — `markArea.data` só tem a faixa verde; sem itens X.

- [ ] **Step 3: Implementar**

Em `chartOption.ts`, adicionar import:

```ts
import { DEFAULT_STALE_MS } from '../lib/freshness'
```

Trocar a assinatura de `buildChartOption` para incluir os 3 params novos no fim (ver bloco Interfaces).

Substituir o bloco do `const markArea = threshold ? {...} : undefined` por construção acumulativa:

```ts
  // markArea unico por serie: acumula faixa verde (Y) + faixas fora-limite (X)
  // + faixa de silencio (X). itemStyle agora e POR ITEM (cores diferem), entao
  // sai do root. Ordem = z-order: verde (fundo) -> vermelhas -> cinza.
  type AreaPair = [Record<string, unknown>, Record<string, unknown>]
  const areaData: AreaPair[] = []

  if (threshold) {
    areaData.push([
      { yAxis: threshold.limite_min, itemStyle: { color: goodSoftColor, opacity: 0.5 } },
      { yAxis: threshold.limite_max },
    ])
    for (const b of computeOutOfRangeBands(data, threshold)) {
      areaData.push([
        { xAxis: b.inicio, itemStyle: { color: critSoftColor, opacity: 0.55 }, name: `${b.direcao} do limite` },
        { xAxis: b.fim },
      ])
    }
  }

  // Faixa de silencio: do ultimo ponto ate `now`, se o silencio ja passou de
  // stale. Gatilho por gap de dado (nao pelo tier), calculado aqui a partir de
  // `now` -- assim o dashboard abrindo com sensor parado ha 1h ja mostra o buraco.
  if (now != null && data.length > 0) {
    const ultimoTs = data[data.length - 1][0]
    if (now - ultimoTs > DEFAULT_STALE_MS) {
      areaData.push([
        { xAxis: ultimoTs, itemStyle: { color: mutedColor, opacity: 0.25 }, name: 'sem dado' },
        { xAxis: now },
      ])
    }
  }

  const markArea = areaData.length ? { data: areaData } : undefined
```

- [ ] **Step 4: Rodar e ver passar**

Run: `npm test -- chartOption`
Expected: PASS (novos + antigos).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/chartOption.ts frontend/src/components/chartOption.test.ts
git commit -m "feat(chart): renderiza faixas fora-de-limite e faixa de silencio no markArea"
```

---

## Task 3: `TimeSeriesChart` passa `now` e cores resolvidas

**Files:**
- Modify: `frontend/src/components/TimeSeriesChart.tsx`
- Test: `frontend/src/components/TimeSeriesChart.test.tsx`

**Interfaces:**
- Consumes: nova assinatura de `buildChartOption` (Task 2).
- Produces: `TimeSeriesChart` ganha prop `now?: number`; resolve `--color-muted` via `useThemeColor` e o passa (junto com `now`) a `buildChartOption`.

> NOTA (ajuste pós-Task 2): a faixa fora-de-limite passou a usar `critColor` (já resolvido/passado hoje) em opacity baixa — o param `critSoftColor` foi REMOVIDO da assinatura. Nova ordem: `buildChartOption(history, threshold, critColor, goodSoftColor, tail, now?, mutedColor?)`. Não resolver nem passar `--color-crit-soft`.

- [ ] **Step 1: Escrever o teste que falha**

Ver o teste existente para replicar o padrão de mock do ECharts:

Run: `sed -n '1,40p' frontend/src/components/TimeSeriesChart.test.tsx`

Adicionar um teste que verifica que `now` é repassado. Como `buildChartOption` é chamada internamente, o teste mais barato é espiar via mock do módulo. Adicionar no topo do arquivo de teste (ajustar se já houver mock de `./chartOption`):

```ts
import { vi } from 'vitest'
const buildSpy = vi.fn(() => ({ series: [{}] }))
vi.mock('./chartOption', () => ({ buildChartOption: (...args: unknown[]) => buildSpy(...args) }))
```

E o teste:

```ts
it('repassa `now` para buildChartOption', () => {
  buildSpy.mockClear()
  render(<TimeSeriesChart history={undefined} threshold={null} tail={[]} now={12345} />)
  // now e o 6o argumento posicional (history, threshold, crit, goodSoft, tail, now, mutedColor)
  expect(buildSpy.mock.calls.at(-1)?.[5]).toBe(12345)
})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `npm test -- TimeSeriesChart`
Expected: FAIL — `now` chega `undefined` (prop não existe / não repassada).

- [ ] **Step 3: Implementar**

Em `TimeSeriesChart.tsx`:

Adicionar `now` às props (tipo e destructuring):

```ts
export function TimeSeriesChart({
  history, threshold, tail, status, now,
}: {
  history: HistoryResponse | undefined
  threshold: Threshold | null
  tail: LivePoint[]
  status?: 'loading' | 'error'
  now?: number
}) {
```

Resolver a cor nova (perto de `critColor`/`goodSoftColor`):

```ts
  const mutedColor = useThemeColor('--color-muted')
```

Atualizar a chamada e as deps do `useEffect`:

```ts
  useEffect(() => {
    chart.current?.setOption(
      buildChartOption(history, threshold, critColor, goodSoftColor, tail, now, mutedColor),
      { notMerge: true },
    )
  }, [history, threshold, critColor, goodSoftColor, tail, now, mutedColor, chart])
```

- [ ] **Step 4: Rodar e ver passar**

Run: `npm test -- TimeSeriesChart`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/TimeSeriesChart.tsx frontend/src/components/TimeSeriesChart.test.tsx
git commit -m "feat(chart): TimeSeriesChart repassa now e cores de faixa resolvidas"
```

---

## Task 4: `KpiWidget` — badge de frescor + número atenuado

**Files:**
- Modify: `frontend/src/components/widgets/KpiWidget.tsx`
- Test: `frontend/src/components/widgets/KpiWidget.test.tsx`

**Interfaces:**
- Consumes: `useNow` de `../../lib/useNow`; `freshness` de `../../lib/freshness`; `FreshnessBadge` de `../FreshnessBadge`.
- Produces: nada consumido por outra task.

Comportamento: `tier = freshness(last ?? undefined, now)`. `tier !== 'fresh'` → cor do número vira `var(--color-muted)`, `opacity: .7`; a atenuação vence a cor de estado (inclusive `crit` do override). Badge à direita do título quando `tier !== 'fresh'`.

- [ ] **Step 1: Escrever os testes que falham**

O `KpiWidget.test.tsx` mocka `useLiveTail` mas não `useNow`. Adicionar mock de `useNow` retornando um `now` fixo, e usar `ts` no `last` para controlar o tier. Adicionar no topo (após os outros `vi.mock`):

```ts
vi.mock('../../lib/useNow', () => ({ useNow: () => 1_000_000 }))
```

Testes novos (dentro do `describe('KpiWidget', ...)`):

```ts
  it('sensor fresh: sem badge de frescor', () => {
    mockUseLiveTail.mockReturnValue({ last: { value: 10, alarm_state: 'ok', ts: 1_000_000 } })
    renderWithClient(<KpiWidget sensorCode="S1" />)
    expect(screen.queryByTestId('freshness-badge')).not.toBeInTheDocument()
  })

  it('sensor offline: mostra badge e atenua o numero', () => {
    // ts 20min atras (> DEFAULT_OFFLINE_MS 15min) -> tier offline
    mockUseLiveTail.mockReturnValue({ last: { value: 10, alarm_state: 'ok', ts: 1_000_000 - 20 * 60_000 } })
    renderWithClient(<KpiWidget sensorCode="S1" />)
    expect(screen.getByTestId('freshness-badge')).toBeInTheDocument()
    const valor = screen.getByText('10')
    expect(valor.style.color).toBe('var(--color-muted)')
  })

  it('offline atenua mesmo com override fora da faixa (nao grita crit)', () => {
    mockUseLiveTail.mockReturnValue({ last: { value: 999, alarm_state: 'ok', ts: 1_000_000 - 20 * 60_000 } })
    renderWithClient(<KpiWidget sensorCode="S1" limiteMin={0} limiteMax={50} />)
    const valor = screen.getByText('999')
    expect(valor.style.color).toBe('var(--color-muted)')
  })
```

Nota p/ o implementador: os testes existentes que passam `last` sem `ts` (ex.: `{ value: 10, alarm_state: 'ok' }`) farão `freshness` ver `ts: undefined` → `now - undefined = NaN` → `NaN <= staleMs` é `false` → cai em `offline`. **Isso quebraria testes antigos.** Ajuste: nesses testes antigos que não se importam com frescor, adicionar `ts: 1_000_000` ao `last` para mantê-los `fresh`. Faça essa varredura no Step 3.

- [ ] **Step 2: Rodar e ver falhar**

Run: `npm test -- KpiWidget`
Expected: FAIL — sem badge; cor não atenua.

- [ ] **Step 3: Implementar**

Em `KpiWidget.tsx`:

Imports:

```ts
import { useNow } from '../../lib/useNow'
import { freshness } from '../../lib/freshness'
import { FreshnessBadge } from '../FreshnessBadge'
```

Após `const { last } = useLiveTail(sensorCode)`:

```ts
  const now = useNow()
  const tier = freshness(last ?? undefined, now)
  const ageMs = last ? now - last.ts : undefined
```

Trocar o cálculo de `cor` para curto-circuitar por tier (a atenuação vence tudo):

```ts
  const cor =
    tier !== 'fresh'
      ? 'var(--color-muted)'
      : state === 'ok' || state === 'unknown'
        ? 'var(--color-ink)'
        : statusTextColor(state)
```

No `<span>` do valor, aplicar opacity quando não-fresh — adicionar ao `style`:

```ts
            opacity: tier !== 'fresh' ? 0.7 : undefined,
```

No header, trocar o `<p>` do título por uma linha flex com o badge:

```tsx
      <div className="flex items-center gap-2">
        <p
          className="min-w-0 flex-1 truncate text-xs font-bold uppercase tracking-wide"
          style={{ color: 'var(--color-muted)' }}
        >
          {titulo}
        </p>
        {tier !== 'fresh' && <FreshnessBadge tier={tier} ageMs={ageMs} />}
      </div>
```

Varredura dos testes antigos: em `KpiWidget.test.tsx`, todo `mockUseLiveTail.mockReturnValue({ last: { ... } })` que NÃO define `ts` e que espera cor de estado/valor visível deve ganhar `ts: 1_000_000` para permanecer `fresh`. (Os que usam `last: null` não mudam — `tier` vira `never`, mas não renderizam número colorido; conferir cada asserção.)

- [ ] **Step 4: Rodar e ver passar**

Run: `npm test -- KpiWidget`
Expected: PASS (novos + antigos ajustados).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/widgets/KpiWidget.tsx frontend/src/components/widgets/KpiWidget.test.tsx
git commit -m "feat(kpi): sinaliza sensor offline com badge de frescor e numero atenuado"
```

---

## Task 5: `TimeseriesWidget` — badge de frescor + passa `now`

**Files:**
- Modify: `frontend/src/components/widgets/TimeseriesWidget.tsx`
- Test: `frontend/src/components/widgets/TimeseriesWidget.test.tsx`

**Interfaces:**
- Consumes: `useNow`; `freshness`; `FreshnessBadge`; `last` de `useLiveTail`; prop `now` de `TimeSeriesChart` (Task 3).
- Produces: nada consumido por outra task.

- [ ] **Step 1: Escrever o teste que falha**

`TimeseriesWidget.test.tsx` mocka `useLiveTail` como `() => ({ tail: [] })` — precisa devolver `last` também, e mockar `useNow`. Ajustar o mock no topo e adicionar teste:

```ts
vi.mock('../../lib/useNow', () => ({ useNow: () => 1_000_000 }))
```

Trocar o mock de `useLiveTail` para permitir configurar `last`:

```ts
const mockTail = vi.fn(() => ({ tail: [], last: null as unknown }))
vi.mock('../../lib/useLiveTail', () => ({ useLiveTail: () => mockTail() }))
```

Teste novo:

```ts
  it('mostra badge de frescor quando o ultimo dado esta offline', () => {
    mockTail.mockReturnValue({ tail: [], last: { value: 10, alarm_state: 'ok', ts: 1_000_000 - 20 * 60_000 } })
    wrap(<TimeseriesWidget sensorCode="S1" />)
    expect(screen.getByTestId('freshness-badge')).toBeInTheDocument()
  })

  it('sensor fresh: sem badge', () => {
    mockTail.mockReturnValue({ tail: [], last: { value: 10, alarm_state: 'ok', ts: 1_000_000 } })
    wrap(<TimeseriesWidget sensorCode="S1" />)
    expect(screen.queryByTestId('freshness-badge')).not.toBeInTheDocument()
  })
```

Nota: os testes existentes chamam `useLiveTail` sem `last`; como agora o mock devolve `last: null` por padrão via `mockTail`, `tier` vira `never` e o badge apareceria ("aguardando dado"), o que quebraria "mostra titulo do sensor e o seletor de janela" se ele assumir ausência de badge — não assume, mas confira. Para os dois testes antigos, definir `mockTail.mockReturnValue({ tail: [], last: { value: 1, alarm_state: 'ok', ts: 1_000_000 } })` no início de cada um (fresh → sem badge).

- [ ] **Step 2: Rodar e ver falhar**

Run: `npm test -- TimeseriesWidget`
Expected: FAIL — sem badge.

- [ ] **Step 3: Implementar**

Em `TimeseriesWidget.tsx`:

Imports:

```ts
import { useNow } from '../../lib/useNow'
import { freshness } from '../../lib/freshness'
import { FreshnessBadge } from '../FreshnessBadge'
```

Trocar `const { tail } = useLiveTail(sensorCode)` por:

```ts
  const { tail, last } = useLiveTail(sensorCode)
  const now = useNow()
  const tier = freshness(last ?? undefined, now)
  const ageMs = last ? now - last.ts : undefined
```

No header, entre o nome e o `WindowSelector`, inserir o badge:

```tsx
        <span className="truncate text-sm font-bold" style={{ color: 'var(--color-ink)' }}>
          {sensor?.name ?? sensorCode}
        </span>
        {tier !== 'fresh' && <FreshnessBadge tier={tier} ageMs={ageMs} />}
        <div className="ml-auto">
          <WindowSelector value={window} onChange={setWindow} />
        </div>
```

Passar `now` ao chart:

```tsx
        <TimeSeriesChart
          history={history.data}
          threshold={threshold.data ?? null}
          tail={tail}
          now={now}
          status={history.isError ? 'error' : history.isLoading ? 'loading' : undefined}
        />
```

- [ ] **Step 4: Rodar e ver passar**

Run: `npm test -- TimeseriesWidget`
Expected: PASS.

- [ ] **Step 5: Rodar a suite inteira**

Run: `npm test`
Expected: PASS — 421 + novos testes, tudo verde.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/widgets/TimeseriesWidget.tsx frontend/src/components/widgets/TimeseriesWidget.test.tsx
git commit -m "feat(timeseries): badge de frescor no header e faixa de silencio no grafico"
```

---

## Verificação visual (após todas as tasks)

Fora do ciclo TDD — verificação no navegador (Playwright/`npm run shot` ou dashboard live em `.env.mock.local`), porque a mistura de cores das faixas (verde 0.5 × vermelho 0.55 na interseção) e as opacidades finais só se avaliam à vista:

- KPI com sensor parado: badge presente, número em cinza atenuado.
- Gráfico: faixa vermelha sob as excursões, faixa cinza no fim quando parado, faixa verde ainda legível por baixo.
- Tema claro e escuro (as cores vêm de `useThemeColor`, re-resolvidas na troca).

---

## Self-Review

**Spec coverage:**
- KPI offline (badge + atenuado) → Task 4. ✓
- Chart offline (badge + faixa de silêncio) → Tasks 3+5 (badge/now) e Task 2 (faixa de silêncio). ✓
- Faixas fora-de-limite derivadas → Tasks 1 (fn) + 2 (render). ✓
- `avg` em agg → coberto por `computeOutOfRangeBands` operar sobre `data` (que já é avg em agg, `chartOption.ts:25`); teste em Task 1 usa a série já plotada. ✓
- Mesma cor acima/abaixo, direção no label → Task 2 (`name`). ✓
- `now` injetado, nunca `Date.now()` → Tasks 2/3/4/5. ✓
- Silêncio por gap (tier-agnóstico), aparece com `never` no load → Task 2 gatilho por `now - ultimoTs`. ✓

**Placeholder scan:** sem TBD/TODO; todo passo tem código concreto. ✓

**Type consistency:** `computeOutOfRangeBands(data, threshold)` e `Banda` idênticos entre Task 1 e Task 2. Assinatura de `buildChartOption` idêntica entre Task 2 e Task 3. `freshness(last ?? undefined, now)` idêntico em Tasks 4 e 5. ✓
