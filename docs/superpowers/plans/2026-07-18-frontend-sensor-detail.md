# Frontend Sentinela CME — Detalhe do Sensor: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir a tela "Detalhe do Sensor" da SPA Sentinela CME contra dados mockados, provando o loop histórico-fetch + cauda-ao-vivo-append.

**Architecture:** Vite+React+TS SPA. Componentes nunca tocam `fetch`/`EventSource` — tudo passa por 3 adapters em `lib/api/` (meta/history/live) selecionáveis por `VITE_API_MODE`. TanStack Query por cima de meta/history; um hook de subscribe para a cauda ao vivo. ECharts recebe a série histórica uma vez e recebe pontos ao vivo via `appendData`, sem refetch.

**Tech Stack:** Vite, React 18, TypeScript, Tailwind CSS v4 (tokens OKLCH), TanStack Query v5, ECharts 5, Vitest + Testing Library + jsdom.

## Global Constraints

- **Local do projeto:** `frontend/` na raiz de `odoo_sentinela/`. Todos os caminhos abaixo são relativos a `frontend/`.
- **Seam mock→real:** nenhum componente chama `fetch`/`EventSource` direto; só via `lib/api/`. Trocar impl real depois **não** toca componentes.
- **Cor = significado:** verde/âmbar/vermelho = estado ambiental e nada mais. Primary azul-frio (`oklch(0.55 0.13 245)`) só para interativo. Status sempre cor **+ ícone + rótulo** (nunca só cor).
- **Contraste:** corpo ≥4.5:1; texto grande ≥3:1.
- **Temas:** light (default) + dark, cada um afinado. `prefers-color-scheme` + classe `.dark`.
- **Prova arquitetural:** histórico busca 1×; cauda ao vivo anexa incremental sem refetch. É o que os testes das Tasks 8–9 verificam.
- **Idioma da UI:** português. Rótulos de status: "Dentro da faixa" / "Perto do limite" / "Fora da faixa".
- **Contratos de dados** casam com campos reais de `odoo_modelo_dados_spec.md` (ver Task 2 / `CONTRACTS.md`).
- **TDD:** teste falha → implementação mínima → teste passa → commit. Commits frequentes.

---

## File Structure

```
frontend/
├── index.html, package.json, vite.config.ts, tsconfig*.json
├── CONTRACTS.md                         # contrato de-facto dos 3 transportes
├── src/
│   ├── main.tsx                          # entry: QueryClientProvider + tema
│   ├── App.tsx                           # rota única → SensorDetailPage
│   ├── index.css                         # @import tailwind + @theme tokens OKLCH
│   ├── lib/
│   │   ├── types.ts                      # SensorMeta, Threshold, HistoryResponse, LivePoint
│   │   ├── status.ts                     # computeStatus(value, threshold)
│   │   ├── api/
│   │   │   ├── contracts.ts              # interfaces MetaApi/HistoryApi/LiveApi
│   │   │   ├── index.ts                  # seleciona mock|real por VITE_API_MODE
│   │   │   └── mock/{fixtures,metaApi,historyApi,liveApi}.ts
│   │   ├── queries.ts                    # useSensorMeta / useThreshold / useHistory
│   │   └── useLiveTail.ts                # subscribe + buffer local
│   ├── components/
│   │   ├── LiveReadout.tsx
│   │   ├── ToleranceRail.tsx
│   │   ├── WindowSelector.tsx
│   │   ├── ThresholdBadge.tsx
│   │   ├── TimeSeriesChart.tsx
│   │   ├── chartOption.ts                # buildChartOption() puro (testável sem canvas)
│   │   └── useECharts.ts                 # init/dispose/resize
│   └── pages/SensorDetailPage.tsx
└── (testes colocados: *.test.ts / *.test.tsx)
```

Princípio de testabilidade: a lógica pura (status, chartOption, adapters mock, buffer) é extraída de componentes para funções/hook testáveis sem canvas. ECharts é mockado nos testes de componente.

---

### Task 1: Scaffold do projeto (Vite + Tailwind v4 + Vitest)

**Files:**
- Create: `frontend/` (via Vite), `frontend/vite.config.ts`, `frontend/src/index.css`, `frontend/src/test/setup.ts`, `frontend/src/smoke.test.ts`

**Interfaces:**
- Produces: projeto que roda (`npm run dev`) e testa (`npm test`); tokens de tema em `index.css`.

- [ ] **Step 1: Scaffold Vite + deps**

```bash
cd /home/afonso/docker/odoo_sentinela
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install @tanstack/react-query echarts
npm install -D tailwindcss @tailwindcss/vite vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```

- [ ] **Step 2: Configurar Vite (Tailwind + Vitest)**

Substituir `frontend/vite.config.ts`:

```ts
/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
})
```

- [ ] **Step 3: Setup de teste + tokens de tema**

`frontend/src/test/setup.ts`:

```ts
import '@testing-library/jest-dom'
```

Substituir `frontend/src/index.css` (tokens OKLCH da direção "instrumento calibrado"):

```css
@import "tailwindcss";

@theme {
  --color-bg: oklch(0.99 0.002 245);
  --color-surface: oklch(1 0 0);
  --color-panel: oklch(0.975 0.003 245);
  --color-ink: oklch(0.24 0.01 245);
  --color-muted: oklch(0.52 0.01 245);
  --color-line: oklch(0.92 0.004 245);
  --color-primary: oklch(0.55 0.13 245);
  --color-good: oklch(0.62 0.15 150);
  --color-warn: oklch(0.68 0.15 75);
  --color-crit: oklch(0.55 0.19 25);
  --font-mono: "Geist Mono", ui-monospace, "SF Mono", Menlo, monospace;
}

.dark {
  --color-bg: oklch(0.16 0.008 245);
  --color-surface: oklch(0.21 0.01 245);
  --color-panel: oklch(0.19 0.009 245);
  --color-ink: oklch(0.95 0.005 245);
  --color-muted: oklch(0.68 0.01 245);
  --color-line: oklch(0.30 0.01 245);
  --color-primary: oklch(0.70 0.13 245);
  --color-good: oklch(0.72 0.16 150);
  --color-warn: oklch(0.78 0.15 75);
  --color-crit: oklch(0.68 0.20 25);
}

body { background: var(--color-bg); color: var(--color-ink); }
```

- [ ] **Step 4: Escrever smoke test**

`frontend/src/smoke.test.ts`:

```ts
import { describe, it, expect } from 'vitest'

describe('smoke', () => {
  it('roda o test runner', () => {
    expect(1 + 1).toBe(2)
  })
})
```

- [ ] **Step 5: Adicionar script de teste**

Em `frontend/package.json`, no bloco `"scripts"`, adicionar: `"test": "vitest run"`, `"test:watch": "vitest"`.

- [ ] **Step 6: Rodar teste (deve passar)**

Run: `cd frontend && npm test`
Expected: PASS — 1 teste (smoke).

- [ ] **Step 7: Verificar build/dev**

Run: `cd frontend && npm run build`
Expected: build sem erro TypeScript.

- [ ] **Step 8: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add frontend/ && git commit -m "feat(frontend): scaffold Vite+React+TS, Tailwind v4 tokens, Vitest"
```

---

### Task 2: Tipos de domínio + lógica de status + CONTRACTS.md

**Files:**
- Create: `src/lib/types.ts`, `src/lib/status.ts`, `src/lib/status.test.ts`, `frontend/CONTRACTS.md`

**Interfaces:**
- Produces:
  - `SensorMeta`, `Threshold`, `HistoryPoint`, `HistoryResponse`, `LivePoint`, `Window` (tipos).
  - `computeStatus(value: number, t: Threshold | null): StatusResult` onde `StatusResult = { state: 'ok'|'warn'|'crit'|'unknown'; label: string; position: number | null }`. `position` = fração 0..1 do valor dentro de [min,max] (clamp), `null` se sem threshold.

- [ ] **Step 1: Escrever tipos**

`src/lib/types.ts`:

```ts
export type Window = '1h' | '24h' | '7d' | '30d'

export type SensorMeta = {
  sensor_code: string
  name: string
  unidade: string
  protocolo_origem: '4-20ma' | 'rs485' | 'i2c'
  measurement_type: { code: string; name: string }
  area: { area_code: string; name: string; category: string }
}

export type Threshold = {
  sensor_id: string
  limite_min: number
  limite_max: number
  is_valor_padrao_regulatorio: boolean
}

export type HistoryPoint =
  | { ts: number; value: number }
  | { ts: number; min: number; max: number; avg: number }

export type HistoryResponse = {
  sensor_code: string
  window: Window
  resolution: 'raw' | 'agg'
  points: HistoryPoint[]
}

export type AlarmState = 'ok' | 'warn' | 'crit'

export type LivePoint = {
  sensor_code: string
  ts: number
  value: number
  alarm_state: AlarmState
}
```

- [ ] **Step 2: Escrever teste de status (falha)**

`src/lib/status.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { computeStatus } from './status'
import type { Threshold } from './types'

const t: Threshold = { sensor_id: 'S1', limite_min: 18, limite_max: 22, is_valor_padrao_regulatorio: true }

describe('computeStatus', () => {
  it('ok no centro da faixa', () => {
    const r = computeStatus(20, t)
    expect(r.state).toBe('ok')
    expect(r.label).toBe('Dentro da faixa')
    expect(r.position).toBeCloseTo(0.5, 5)
  })
  it('warn perto do limite superior', () => {
    expect(computeStatus(21.8, t).state).toBe('warn')
  })
  it('warn perto do limite inferior', () => {
    expect(computeStatus(18.2, t).state).toBe('warn')
  })
  it('crit acima do maximo', () => {
    const r = computeStatus(23, t)
    expect(r.state).toBe('crit')
    expect(r.label).toBe('Fora da faixa')
    expect(r.position).toBe(1) // clamp
  })
  it('crit abaixo do minimo', () => {
    expect(computeStatus(17, t).position).toBe(0) // clamp
  })
  it('unknown sem threshold', () => {
    const r = computeStatus(20, null)
    expect(r.state).toBe('unknown')
    expect(r.position).toBeNull()
  })
})
```

- [ ] **Step 3: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/lib/status.test.ts`
Expected: FAIL — `computeStatus` não existe.

- [ ] **Step 4: Implementar status**

`src/lib/status.ts`:

```ts
import type { Threshold } from './types'

export type StatusResult = {
  state: 'ok' | 'warn' | 'crit' | 'unknown'
  label: string
  position: number | null
}

const LABELS = {
  ok: 'Dentro da faixa',
  warn: 'Perto do limite',
  crit: 'Fora da faixa',
  unknown: 'Sem limite',
} as const

// Margem de "perto do limite": 10% da largura da faixa em cada borda.
const WARN_MARGIN = 0.1

export function computeStatus(value: number, t: Threshold | null): StatusResult {
  if (!t) return { state: 'unknown', label: LABELS.unknown, position: null }
  const range = t.limite_max - t.limite_min
  const raw = range > 0 ? (value - t.limite_min) / range : 0.5
  const position = Math.min(1, Math.max(0, raw))
  let state: StatusResult['state']
  if (value < t.limite_min || value > t.limite_max) state = 'crit'
  else if (raw < WARN_MARGIN || raw > 1 - WARN_MARGIN) state = 'warn'
  else state = 'ok'
  return { state, label: LABELS[state], position }
}
```

- [ ] **Step 5: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/lib/status.test.ts`
Expected: PASS — 6 testes.

- [ ] **Step 6: Escrever CONTRACTS.md**

`frontend/CONTRACTS.md` documenta os 4 shapes (copiar de `types.ts`) + mapeamento a campos Odoo reais: `SensorMeta`←`sensor_monitor.sensor`+`area`+`measurement.type`; `Threshold`←`alarm.threshold` (`limite_min`/`limite_max`/`is_valor_padrao_regulatorio`); `HistoryResponse`←API de leitura Timescale (raw p/ 1h, agg p/ janelas longas); `LivePoint`←feed SSE. Marcar: "contrato de-facto — Fase 3 real deve respeitar estes shapes."

- [ ] **Step 7: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add frontend/src/lib/types.ts frontend/src/lib/status.ts frontend/src/lib/status.test.ts frontend/CONTRACTS.md
git commit -m "feat(frontend): tipos de dominio, computeStatus, CONTRACTS.md"
```

---

### Task 3: Adapters mock (meta / history / live)

**Files:**
- Create: `src/lib/api/contracts.ts`, `src/lib/api/mock/fixtures.ts`, `src/lib/api/mock/metaApi.ts`, `src/lib/api/mock/historyApi.ts`, `src/lib/api/mock/liveApi.ts`, `src/lib/api/mock/mock.test.ts`

**Interfaces:**
- Produces:
  - `MetaApi = { getSensor(code): Promise<SensorMeta>; getThreshold(code): Promise<Threshold | null> }`
  - `HistoryApi = { getHistory(code, window): Promise<HistoryResponse> }`
  - `LiveApi = { subscribe(code, cb: (p: LivePoint) => void): () => void }` (retorna unsubscribe)
  - Impls mock: `mockMetaApi`, `mockHistoryApi`, `mockLiveApi`.

- [ ] **Step 1: Escrever interfaces**

`src/lib/api/contracts.ts`:

```ts
import type { SensorMeta, Threshold, HistoryResponse, LivePoint, Window } from '../types'

export type MetaApi = {
  getSensor(code: string): Promise<SensorMeta>
  getThreshold(code: string): Promise<Threshold | null>
}
export type HistoryApi = {
  getHistory(code: string, window: Window): Promise<HistoryResponse>
}
export type LiveApi = {
  subscribe(code: string, cb: (p: LivePoint) => void): () => void
}
```

- [ ] **Step 2: Escrever fixtures**

`src/lib/api/mock/fixtures.ts`:

```ts
import type { SensorMeta, Threshold } from '../../types'

export const SENSOR: SensorMeta = {
  sensor_code: 'TEMP-EXP-01',
  name: 'Temperatura — Expurgo',
  unidade: 'C',
  protocolo_origem: 'rs485',
  measurement_type: { code: 'temperatura', name: 'Temperatura' },
  area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' },
}

export const THRESHOLD: Threshold = {
  sensor_id: 'TEMP-EXP-01',
  limite_min: 18,
  limite_max: 22,
  is_valor_padrao_regulatorio: true,
}
```

- [ ] **Step 3: Escrever teste dos adapters (falha)**

`src/lib/api/mock/mock.test.ts`:

```ts
import { describe, it, expect, vi, afterEach } from 'vitest'
import { mockMetaApi } from './metaApi'
import { mockHistoryApi } from './historyApi'
import { mockLiveApi } from './liveApi'

afterEach(() => vi.useRealTimers())

describe('mockMetaApi', () => {
  it('devolve sensor e threshold da fixture', async () => {
    expect((await mockMetaApi.getSensor('x')).sensor_code).toBe('TEMP-EXP-01')
    expect((await mockMetaApi.getThreshold('x'))?.limite_max).toBe(22)
  })
})

describe('mockHistoryApi', () => {
  it('1h = raw, janela longa = agg', async () => {
    expect((await mockHistoryApi.getHistory('x', '1h')).resolution).toBe('raw')
    expect((await mockHistoryApi.getHistory('x', '30d')).resolution).toBe('agg')
  })
  it('nunca devolve mais de 1000 pontos', async () => {
    const r = await mockHistoryApi.getHistory('x', '30d')
    expect(r.points.length).toBeLessThanOrEqual(1000)
    expect(r.points.length).toBeGreaterThan(0)
  })
})

describe('mockLiveApi', () => {
  it('emite pontos incrementais e para no unsubscribe', () => {
    vi.useFakeTimers()
    const cb = vi.fn()
    const unsub = mockLiveApi.subscribe('x', cb)
    vi.advanceTimersByTime(3000)
    const afterThree = cb.mock.calls.length
    expect(afterThree).toBeGreaterThanOrEqual(2)
    unsub()
    vi.advanceTimersByTime(3000)
    expect(cb.mock.calls.length).toBe(afterThree) // parou
  })
  it('cada emissão é UM ponto com timestamp crescente', () => {
    vi.useFakeTimers()
    const pts: number[] = []
    const unsub = mockLiveApi.subscribe('x', (p) => pts.push(p.ts))
    vi.advanceTimersByTime(3000)
    unsub()
    for (let i = 1; i < pts.length; i++) expect(pts[i]).toBeGreaterThan(pts[i - 1])
  })
})
```

- [ ] **Step 4: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/lib/api/mock/mock.test.ts`
Expected: FAIL — módulos não existem.

- [ ] **Step 5: Implementar metaApi mock**

`src/lib/api/mock/metaApi.ts`:

```ts
import type { MetaApi } from '../contracts'
import { SENSOR, THRESHOLD } from './fixtures'

export const mockMetaApi: MetaApi = {
  async getSensor() { return SENSOR },
  async getThreshold() { return THRESHOLD },
}
```

- [ ] **Step 6: Implementar historyApi mock**

`src/lib/api/mock/historyApi.ts`:

```ts
import type { HistoryApi } from '../contracts'
import type { HistoryResponse, HistoryPoint, Window } from '../../types'
import { THRESHOLD } from './fixtures'

const SPAN_MS: Record<Window, number> = {
  '1h': 3_600_000, '24h': 86_400_000, '7d': 604_800_000, '30d': 2_592_000_000,
}

// Série sintética determinística (senoide em torno do meio da faixa + ruído fixo).
function synth(window: Window): { resolution: 'raw' | 'agg'; points: HistoryPoint[] } {
  const span = SPAN_MS[window]
  const now = 1_700_000_000_000 // base fixa (sem Date.now — determinístico p/ teste)
  const mid = (THRESHOLD.limite_min + THRESHOLD.limite_max) / 2
  const amp = (THRESHOLD.limite_max - THRESHOLD.limite_min) / 3
  const n = window === '1h' ? 240 : 720
  const step = span / n
  const raw = window === '1h'
  const points: HistoryPoint[] = []
  for (let i = 0; i < n; i++) {
    const ts = now - span + i * step
    const base = mid + amp * Math.sin(i / 12)
    if (raw) points.push({ ts, value: +base.toFixed(2) })
    else points.push({ ts, min: +(base - amp / 4).toFixed(2), max: +(base + amp / 4).toFixed(2), avg: +base.toFixed(2) })
  }
  return { resolution: raw ? 'raw' : 'agg', points }
}

export const mockHistoryApi: HistoryApi = {
  async getHistory(sensor_code: string, window: Window): Promise<HistoryResponse> {
    const { resolution, points } = synth(window)
    return { sensor_code, window, resolution, points }
  },
}
```

- [ ] **Step 7: Implementar liveApi mock**

`src/lib/api/mock/liveApi.ts`:

```ts
import type { LiveApi } from '../contracts'
import type { LivePoint } from '../../types'
import { THRESHOLD } from './fixtures'
import { computeStatus } from '../../status'

const TICK_MS = 1000

export const mockLiveApi: LiveApi = {
  subscribe(sensor_code, cb) {
    const mid = (THRESHOLD.limite_min + THRESHOLD.limite_max) / 2
    const amp = (THRESHOLD.limite_max - THRESHOLD.limite_min) / 2.2
    let i = 0
    let ts = 1_700_000_000_000
    const id = setInterval(() => {
      ts += TICK_MS
      const value = +(mid + amp * Math.sin(i / 6)).toFixed(2)
      i++
      const state = computeStatus(value, THRESHOLD).state
      const alarm_state = state === 'unknown' ? 'ok' : state
      const point: LivePoint = { sensor_code, ts, value, alarm_state }
      cb(point)
    }, TICK_MS)
    return () => clearInterval(id)
  },
}
```

- [ ] **Step 8: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/lib/api/mock/mock.test.ts`
Expected: PASS — todos.

- [ ] **Step 9: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add frontend/src/lib/api/
git commit -m "feat(frontend): adapters mock meta/history/live com testes"
```

---

### Task 4: Seletor de API + hooks TanStack Query

**Files:**
- Create: `src/lib/api/index.ts`, `src/lib/queries.ts`, `src/lib/queries.test.tsx`

**Interfaces:**
- Consumes: `mockMetaApi`, `mockHistoryApi`, `mockLiveApi`, `MetaApi/HistoryApi/LiveApi`.
- Produces:
  - `metaApi`, `historyApi`, `liveApi` (selecionados por `import.meta.env.VITE_API_MODE`).
  - Hooks: `useSensorMeta(code)`, `useThreshold(code)`, `useHistory(code, window)` (retornam `UseQueryResult`).

- [ ] **Step 1: Implementar seletor**

`src/lib/api/index.ts`:

```ts
import type { MetaApi, HistoryApi, LiveApi } from './contracts'
import { mockMetaApi } from './mock/metaApi'
import { mockHistoryApi } from './mock/historyApi'
import { mockLiveApi } from './mock/liveApi'

// Fase 3 (real) entra aqui sem tocar componentes: trocar por impl HTTP/SSE quando VITE_API_MODE=real.
const mode = import.meta.env.VITE_API_MODE ?? 'mock'
if (mode !== 'mock') console.warn(`VITE_API_MODE=${mode} sem impl real ainda; usando mock`)

export const metaApi: MetaApi = mockMetaApi
export const historyApi: HistoryApi = mockHistoryApi
export const liveApi: LiveApi = mockLiveApi
```

- [ ] **Step 2: Escrever teste dos hooks (falha)**

`src/lib/queries.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useSensorMeta, useThreshold, useHistory } from './queries'
import type { ReactNode } from 'react'

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('queries', () => {
  it('useSensorMeta carrega a fixture', async () => {
    const { result } = renderHook(() => useSensorMeta('x'), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.sensor_code).toBe('TEMP-EXP-01')
  })
  it('useHistory 1h = raw', async () => {
    const { result } = renderHook(() => useHistory('x', '1h'), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.resolution).toBe('raw')
  })
  it('useThreshold carrega limites', async () => {
    const { result } = renderHook(() => useThreshold('x'), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.limite_max).toBe(22)
  })
})
```

- [ ] **Step 3: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/lib/queries.test.tsx`
Expected: FAIL — hooks não existem.

- [ ] **Step 4: Implementar hooks**

`src/lib/queries.ts`:

```ts
import { useQuery } from '@tanstack/react-query'
import { metaApi, historyApi } from './api'
import type { Window } from './types'

export function useSensorMeta(code: string) {
  return useQuery({ queryKey: ['sensor', code], queryFn: () => metaApi.getSensor(code) })
}
export function useThreshold(code: string) {
  return useQuery({ queryKey: ['threshold', code], queryFn: () => metaApi.getThreshold(code) })
}
export function useHistory(code: string, window: Window) {
  return useQuery({ queryKey: ['history', code, window], queryFn: () => historyApi.getHistory(code, window) })
}
```

- [ ] **Step 5: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/lib/queries.test.tsx`
Expected: PASS — 3 testes.

- [ ] **Step 6: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add frontend/src/lib/api/index.ts frontend/src/lib/queries.ts frontend/src/lib/queries.test.tsx
git commit -m "feat(frontend): seletor de API por VITE_API_MODE + hooks TanStack Query"
```

---

### Task 5: Hook de cauda ao vivo (useLiveTail)

**Files:**
- Create: `src/lib/useLiveTail.ts`, `src/lib/useLiveTail.test.tsx`

**Interfaces:**
- Consumes: `liveApi`, `LivePoint`.
- Produces: `useLiveTail(code, max = 300): { last: LivePoint | null; tail: LivePoint[] }`. `tail` cresce por append incremental, cap em `max`; desinscreve no unmount.

- [ ] **Step 1: Escrever teste (falha)**

`src/lib/useLiveTail.test.tsx`:

```tsx
import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useLiveTail } from './useLiveTail'

afterEach(() => vi.useRealTimers())

describe('useLiveTail', () => {
  it('acumula pontos incrementais', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useLiveTail('x'))
    expect(result.current.tail.length).toBe(0)
    act(() => { vi.advanceTimersByTime(3000) })
    expect(result.current.tail.length).toBeGreaterThanOrEqual(2)
    expect(result.current.last).not.toBeNull()
  })
  it('respeita o cap max', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useLiveTail('x', 3))
    act(() => { vi.advanceTimersByTime(10000) })
    expect(result.current.tail.length).toBeLessThanOrEqual(3)
  })
  it('desinscreve no unmount (nao vaza timer)', () => {
    vi.useFakeTimers()
    const { result, unmount } = renderHook(() => useLiveTail('x'))
    act(() => { vi.advanceTimersByTime(2000) })
    const n = result.current.tail.length
    unmount()
    act(() => { vi.advanceTimersByTime(5000) })
    expect(result.current.tail.length).toBe(n)
  })
})
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/lib/useLiveTail.test.tsx`
Expected: FAIL — hook não existe.

- [ ] **Step 3: Implementar hook**

`src/lib/useLiveTail.ts`:

```ts
import { useEffect, useRef, useState } from 'react'
import { liveApi } from './api'
import type { LivePoint } from './types'

export function useLiveTail(code: string, max = 300) {
  const [tail, setTail] = useState<LivePoint[]>([])
  const maxRef = useRef(max)
  maxRef.current = max
  useEffect(() => {
    setTail([])
    const unsub = liveApi.subscribe(code, (p) => {
      setTail((prev) => {
        const next = [...prev, p]
        return next.length > maxRef.current ? next.slice(next.length - maxRef.current) : next
      })
    })
    return unsub
  }, [code])
  return { last: tail.length ? tail[tail.length - 1] : null, tail }
}
```

- [ ] **Step 4: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/lib/useLiveTail.test.tsx`
Expected: PASS — 3 testes.

- [ ] **Step 5: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add frontend/src/lib/useLiveTail.ts frontend/src/lib/useLiveTail.test.tsx
git commit -m "feat(frontend): useLiveTail com buffer incremental e cleanup"
```

---

### Task 6: LiveReadout + ToleranceRail (a assinatura)

**Files:**
- Create: `src/components/ToleranceRail.tsx`, `src/components/LiveReadout.tsx`, `src/components/LiveReadout.test.tsx`

**Interfaces:**
- Consumes: `computeStatus`, `Threshold`, `AlarmState`.
- Produces:
  - `<ToleranceRail position={number|null} state={StatusResult['state']} />`
  - `<LiveReadout value={number|null} unidade={string} threshold={Threshold|null} state?={AlarmState} />` — usa `state` do feed se dado, senão deriva de `computeStatus`.

- [ ] **Step 1: Escrever teste (falha)**

`src/components/LiveReadout.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LiveReadout } from './LiveReadout'
import type { Threshold } from '../lib/types'

const t: Threshold = { sensor_id: 'S', limite_min: 18, limite_max: 22, is_valor_padrao_regulatorio: true }

describe('LiveReadout', () => {
  it('mostra valor e unidade', () => {
    render(<LiveReadout value={20.5} unidade="C" threshold={t} />)
    expect(screen.getByText(/20[.,]5/)).toBeInTheDocument()
    expect(screen.getByText('C')).toBeInTheDocument()
  })
  it('status por rotulo textual, nao so cor (ok)', () => {
    render(<LiveReadout value={20} unidade="C" threshold={t} />)
    expect(screen.getByText('Dentro da faixa')).toBeInTheDocument()
  })
  it('crit quando fora da faixa', () => {
    render(<LiveReadout value={25} unidade="C" threshold={t} />)
    expect(screen.getByText('Fora da faixa')).toBeInTheDocument()
  })
  it('estado do feed tem prioridade sobre o derivado', () => {
    render(<LiveReadout value={20} unidade="C" threshold={t} state="crit" />)
    expect(screen.getByText('Fora da faixa')).toBeInTheDocument()
  })
  it('sem valor mostra placeholder', () => {
    render(<LiveReadout value={null} unidade="C" threshold={t} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/components/LiveReadout.test.tsx`
Expected: FAIL — componente não existe.

- [ ] **Step 3: Implementar ToleranceRail**

`src/components/ToleranceRail.tsx`:

```tsx
import type { StatusResult } from '../lib/status'

const DOT: Record<StatusResult['state'], string> = {
  ok: 'var(--color-good)', warn: 'var(--color-warn)', crit: 'var(--color-crit)', unknown: 'var(--color-muted)',
}

export function ToleranceRail({ position, state }: { position: number | null; state: StatusResult['state'] }) {
  const pct = position === null ? 50 : position * 100
  return (
    <div className="relative h-2 rounded-full" style={{ background: 'var(--color-line)' }} aria-hidden>
      <div className="absolute inset-y-0 rounded-full" style={{ left: '10%', right: '10%', background: 'var(--color-good)', opacity: 0.25 }} />
      {position !== null && (
        <div className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-white"
             style={{ left: `${pct}%`, background: DOT[state] }} />
      )}
    </div>
  )
}
```

- [ ] **Step 4: Implementar LiveReadout**

`src/components/LiveReadout.tsx`:

```tsx
import { computeStatus } from '../lib/status'
import type { Threshold, AlarmState } from '../lib/types'
import { ToleranceRail } from './ToleranceRail'

const COLOR = {
  ok: 'var(--color-good)', warn: 'var(--color-warn)', crit: 'var(--color-crit)', unknown: 'var(--color-muted)',
} as const
const ICON = { ok: '●', warn: '▲', crit: '■', unknown: '○' } as const
const LABEL = { ok: 'Dentro da faixa', warn: 'Perto do limite', crit: 'Fora da faixa', unknown: 'Sem limite' } as const

export function LiveReadout({
  value, unidade, threshold, state,
}: { value: number | null; unidade: string; threshold: Threshold | null; state?: AlarmState }) {
  const derived = value !== null ? computeStatus(value, threshold) : { state: 'unknown' as const, label: LABEL.unknown, position: null }
  const st = state ?? derived.state
  return (
    <div className="rounded-xl p-6" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}>
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-6xl tabular-nums" style={{ color: 'var(--color-ink)' }}>
          {value === null ? '—' : value.toFixed(1)}
        </span>
        <span className="text-xl" style={{ color: 'var(--color-muted)' }}>{unidade}</span>
      </div>
      <div className="mt-3 flex items-center gap-2 text-sm font-semibold" style={{ color: COLOR[st] }}>
        <span aria-hidden>{ICON[st]}</span>
        <span>{LABEL[st]}</span>
      </div>
      <div className="mt-4">
        <ToleranceRail position={derived.position} state={st} />
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/components/LiveReadout.test.tsx`
Expected: PASS — 5 testes.

- [ ] **Step 6: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add frontend/src/components/ToleranceRail.tsx frontend/src/components/LiveReadout.tsx frontend/src/components/LiveReadout.test.tsx
git commit -m "feat(frontend): LiveReadout + ToleranceRail (assinatura instrumento calibrado)"
```

---

### Task 7: WindowSelector + ThresholdBadge

**Files:**
- Create: `src/components/WindowSelector.tsx`, `src/components/ThresholdBadge.tsx`, `src/components/controls.test.tsx`

**Interfaces:**
- Consumes: `Window`, `Threshold`.
- Produces:
  - `<WindowSelector value={Window} onChange={(w: Window) => void} />`
  - `<ThresholdBadge threshold={Threshold | null} unidade={string} />`

- [ ] **Step 1: Escrever teste (falha)**

`src/components/controls.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { WindowSelector } from './WindowSelector'
import { ThresholdBadge } from './ThresholdBadge'
import type { Threshold } from '../lib/types'

const t: Threshold = { sensor_id: 'S', limite_min: 18, limite_max: 22, is_valor_padrao_regulatorio: true }

describe('WindowSelector', () => {
  it('marca a janela ativa e emite onChange', async () => {
    const onChange = vi.fn()
    render(<WindowSelector value="24h" onChange={onChange} />)
    const btn = screen.getByRole('button', { name: '24h' })
    expect(btn).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: '7d' }))
    expect(onChange).toHaveBeenCalledWith('7d')
  })
})

describe('ThresholdBadge', () => {
  it('mostra min/max e marca padrao regulatorio', () => {
    render(<ThresholdBadge threshold={t} unidade="C" />)
    expect(screen.getByText(/18/)).toBeInTheDocument()
    expect(screen.getByText(/22/)).toBeInTheDocument()
    expect(screen.getByText(/RDC 15|regulat/i)).toBeInTheDocument()
  })
  it('sem threshold mostra "sem limite"', () => {
    render(<ThresholdBadge threshold={null} unidade="C" />)
    expect(screen.getByText(/sem limite/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/components/controls.test.tsx`
Expected: FAIL — componentes não existem.

- [ ] **Step 3: Implementar WindowSelector**

`src/components/WindowSelector.tsx`:

```tsx
import type { Window } from '../lib/types'

const WINDOWS: Window[] = ['1h', '24h', '7d', '30d']

export function WindowSelector({ value, onChange }: { value: Window; onChange: (w: Window) => void }) {
  return (
    <div className="inline-flex gap-1 rounded-lg p-1" style={{ background: 'var(--color-panel)' }} role="group" aria-label="Janela temporal">
      {WINDOWS.map((w) => {
        const on = w === value
        return (
          <button key={w} type="button" aria-pressed={on} onClick={() => onChange(w)}
            className="rounded-md px-3 py-1.5 text-sm font-semibold transition-colors"
            style={on
              ? { background: 'var(--color-primary)', color: 'white' }
              : { color: 'var(--color-muted)' }}>
            {w}
          </button>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 4: Implementar ThresholdBadge**

`src/components/ThresholdBadge.tsx`:

```tsx
import type { Threshold } from '../lib/types'

export function ThresholdBadge({ threshold, unidade }: { threshold: Threshold | null; unidade: string }) {
  if (!threshold) {
    return <span className="text-sm" style={{ color: 'var(--color-muted)' }}>Sem limite configurado</span>
  }
  return (
    <div className="flex items-center gap-3 text-sm" style={{ color: 'var(--color-muted)' }}>
      <span>Faixa segura: <b style={{ color: 'var(--color-ink)' }}>{threshold.limite_min}–{threshold.limite_max} {unidade}</b></span>
      {threshold.is_valor_padrao_regulatorio && (
        <span className="rounded px-2 py-0.5 text-xs font-semibold"
          style={{ background: 'var(--color-panel)', color: 'var(--color-primary)' }}>Padrão RDC 15</span>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/components/controls.test.tsx`
Expected: PASS — 3 testes.

- [ ] **Step 6: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add frontend/src/components/WindowSelector.tsx frontend/src/components/ThresholdBadge.tsx frontend/src/components/controls.test.tsx
git commit -m "feat(frontend): WindowSelector + ThresholdBadge"
```

---

### Task 8: chartOption (puro) + TimeSeriesChart (a prova arquitetural)

**Files:**
- Create: `src/components/chartOption.ts`, `src/components/chartOption.test.ts`, `src/components/useECharts.ts`, `src/components/TimeSeriesChart.tsx`, `src/components/TimeSeriesChart.test.tsx`

**Interfaces:**
- Consumes: `HistoryResponse`, `Threshold`, `LivePoint`.
- Produces:
  - `buildChartOption(history: HistoryResponse | undefined, threshold: Threshold | null): EChartsOption` — série base + `markLine` em `limite_min`/`limite_max`.
  - `<TimeSeriesChart history={HistoryResponse|undefined} threshold={Threshold|null} tail={LivePoint[]} />` — faz `setOption` no histórico e `appendData` a cada novo ponto da cauda, **sem** reconstruir a série base.

- [ ] **Step 1: Escrever teste de chartOption (falha)**

`src/components/chartOption.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { buildChartOption } from './chartOption'
import type { HistoryResponse, Threshold } from '../lib/types'

const t: Threshold = { sensor_id: 'S', limite_min: 18, limite_max: 22, is_valor_padrao_regulatorio: true }
const hist: HistoryResponse = {
  sensor_code: 'S', window: '1h', resolution: 'raw',
  points: [{ ts: 1000, value: 19 }, { ts: 2000, value: 21 }],
}

describe('buildChartOption', () => {
  it('markLines batem com os limites do threshold', () => {
    const opt = buildChartOption(hist, t) as any
    const marks = opt.series[0].markLine.data.map((d: any) => d.yAxis)
    expect(marks).toContain(18)
    expect(marks).toContain(22)
  })
  it('serie base tem os pontos do historico', () => {
    const opt = buildChartOption(hist, t) as any
    expect(opt.series[0].data).toEqual([[1000, 19], [2000, 21]])
  })
  it('sem threshold nao desenha markLine', () => {
    const opt = buildChartOption(hist, null) as any
    expect(opt.series[0].markLine).toBeUndefined()
  })
  it('sem historico devolve serie vazia', () => {
    const opt = buildChartOption(undefined, t) as any
    expect(opt.series[0].data).toEqual([])
  })
})
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/components/chartOption.test.ts`
Expected: FAIL — `buildChartOption` não existe.

- [ ] **Step 3: Implementar chartOption**

`src/components/chartOption.ts`:

```ts
import type { HistoryResponse, Threshold } from '../lib/types'

export function buildChartOption(history: HistoryResponse | undefined, threshold: Threshold | null) {
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
```

- [ ] **Step 4: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/components/chartOption.test.ts`
Expected: PASS — 4 testes.

- [ ] **Step 5: Implementar hook useECharts**

`src/components/useECharts.ts`:

```ts
import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

export function useECharts() {
  const el = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)
  useEffect(() => {
    if (!el.current) return
    chart.current = echarts.init(el.current)
    const onResize = () => chart.current?.resize()
    window.addEventListener('resize', onResize)
    return () => { window.removeEventListener('resize', onResize); chart.current?.dispose(); chart.current = null }
  }, [])
  return { el, chart }
}
```

- [ ] **Step 6: Escrever teste do componente (falha) — a prova**

`src/components/TimeSeriesChart.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'

const setOption = vi.fn()
const appendData = vi.fn()
const dispose = vi.fn()
vi.mock('echarts', () => ({
  init: () => ({ setOption, appendData, dispose, resize: vi.fn() }),
}))

import { TimeSeriesChart } from './TimeSeriesChart'
import type { HistoryResponse, Threshold, LivePoint } from '../lib/types'

const t: Threshold = { sensor_id: 'S', limite_min: 18, limite_max: 22, is_valor_padrao_regulatorio: true }
const hist: HistoryResponse = { sensor_code: 'S', window: '1h', resolution: 'raw', points: [{ ts: 1000, value: 20 }] }

beforeEach(() => { setOption.mockClear(); appendData.mockClear() })

describe('TimeSeriesChart', () => {
  it('setOption uma vez com o historico; ponto ao vivo usa appendData, NAO setOption de novo', () => {
    const { rerender } = render(<TimeSeriesChart history={hist} threshold={t} tail={[]} />)
    const optionCallsAfterHistory = setOption.mock.calls.length
    expect(optionCallsAfterHistory).toBeGreaterThanOrEqual(1)

    const p: LivePoint = { sensor_code: 'S', ts: 2000, value: 21, alarm_state: 'ok' }
    rerender(<TimeSeriesChart history={hist} threshold={t} tail={[p]} />)

    expect(appendData).toHaveBeenCalledTimes(1)              // anexou o ponto
    expect(setOption.mock.calls.length).toBe(optionCallsAfterHistory) // NAO refez a serie base
  })
})
```

- [ ] **Step 7: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/components/TimeSeriesChart.test.tsx`
Expected: FAIL — componente não existe.

- [ ] **Step 8: Implementar TimeSeriesChart**

`src/components/TimeSeriesChart.tsx`:

```tsx
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
```

- [ ] **Step 9: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/components/TimeSeriesChart.test.tsx`
Expected: PASS — a prova arquitetural (append sem refetch).

- [ ] **Step 10: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add frontend/src/components/chartOption.ts frontend/src/components/chartOption.test.ts frontend/src/components/useECharts.ts frontend/src/components/TimeSeriesChart.tsx frontend/src/components/TimeSeriesChart.test.tsx
git commit -m "feat(frontend): TimeSeriesChart com append da cauda ao vivo (prova arquitetural)"
```

---

### Task 9: SensorDetailPage + wiring do app + tema

**Files:**
- Create: `src/pages/SensorDetailPage.tsx`, `src/pages/SensorDetailPage.test.tsx`, `src/components/ThemeToggle.tsx`
- Modify: `src/App.tsx`, `src/main.tsx`

**Interfaces:**
- Consumes: `useSensorMeta`, `useThreshold`, `useHistory`, `useLiveTail`, todos os componentes.
- Produces: `<SensorDetailPage code={string} />`; app montado com `QueryClientProvider`.

- [ ] **Step 1: Escrever teste de integração (falha)**

`src/pages/SensorDetailPage.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

// ECharts mockado (sem canvas em jsdom)
vi.mock('echarts', () => ({ init: () => ({ setOption: vi.fn(), appendData: vi.fn(), dispose: vi.fn(), resize: vi.fn() }) }))

import { SensorDetailPage } from './SensorDetailPage'
import * as api from '../lib/api'

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{node}</QueryClientProvider>
}

afterEach(() => vi.useRealTimers())

describe('SensorDetailPage', () => {
  it('renderiza nome do sensor, readout e faixa', async () => {
    render(wrap(<SensorDetailPage code="TEMP-EXP-01" />))
    await waitFor(() => expect(screen.getByText(/Temperatura — Expurgo/)).toBeInTheDocument())
    expect(screen.getByText(/Faixa segura/)).toBeInTheDocument()
  })

  it('trocar janela dispara novo fetch de historico (getHistory chamado de novo)', async () => {
    const spy = vi.spyOn(api.historyApi, 'getHistory')
    render(wrap(<SensorDetailPage code="TEMP-EXP-01" />))
    await waitFor(() => expect(spy).toHaveBeenCalledWith('TEMP-EXP-01', '24h'))
    const before = spy.mock.calls.length
    await userEvent.click(screen.getByRole('button', { name: '7d' }))
    await waitFor(() => expect(spy).toHaveBeenCalledWith('TEMP-EXP-01', '7d'))
    expect(spy.mock.calls.length).toBeGreaterThan(before)
    spy.mockRestore()
  })
})
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/pages/SensorDetailPage.test.tsx`
Expected: FAIL — página não existe.

- [ ] **Step 3: Implementar ThemeToggle**

`src/components/ThemeToggle.tsx`:

```tsx
import { useEffect, useState } from 'react'

export function ThemeToggle() {
  const [dark, setDark] = useState(false)
  useEffect(() => { document.documentElement.classList.toggle('dark', dark) }, [dark])
  return (
    <button type="button" onClick={() => setDark((d) => !d)}
      className="rounded-md px-3 py-1.5 text-sm font-semibold"
      style={{ border: '1px solid var(--color-line)', color: 'var(--color-muted)' }}
      aria-pressed={dark}>
      {dark ? 'Claro' : 'Escuro'}
    </button>
  )
}
```

- [ ] **Step 4: Implementar SensorDetailPage**

`src/pages/SensorDetailPage.tsx`:

```tsx
import { useState } from 'react'
import { useSensorMeta, useThreshold, useHistory } from '../lib/queries'
import { useLiveTail } from '../lib/useLiveTail'
import { LiveReadout } from '../components/LiveReadout'
import { WindowSelector } from '../components/WindowSelector'
import { ThresholdBadge } from '../components/ThresholdBadge'
import { TimeSeriesChart } from '../components/TimeSeriesChart'
import { ThemeToggle } from '../components/ThemeToggle'
import type { Window } from '../lib/types'

export function SensorDetailPage({ code }: { code: string }) {
  const [window, setWindow] = useState<Window>('24h')
  const meta = useSensorMeta(code)
  const threshold = useThreshold(code)
  const history = useHistory(code, window)
  const { last, tail } = useLiveTail(code)

  const unidade = meta.data?.unidade ?? ''
  const th = threshold.data ?? null

  return (
    <div className="mx-auto max-w-4xl p-6">
      <header className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--color-ink)' }}>
            {meta.isLoading ? 'Carregando…' : meta.data?.name}
          </h1>
          {meta.data && (
            <p className="text-sm" style={{ color: 'var(--color-muted)' }}>
              {meta.data.area.name} · {meta.data.measurement_type.name}
            </p>
          )}
        </div>
        <ThemeToggle />
      </header>

      <div className="grid gap-6 md:grid-cols-[320px_1fr]">
        <div className="space-y-4">
          <LiveReadout value={last?.value ?? null} unidade={unidade} threshold={th} state={last?.alarm_state} />
          <ThresholdBadge threshold={th} unidade={unidade} />
        </div>

        <div className="rounded-xl p-4" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}>
          <div className="mb-4 flex justify-end">
            <WindowSelector value={window} onChange={setWindow} />
          </div>
          {history.isError ? (
            <div className="flex h-80 items-center justify-center text-sm" style={{ color: 'var(--color-crit)' }}>
              Falha ao carregar histórico.{' '}
              <button className="ml-2 underline" onClick={() => history.refetch()}>Tentar de novo</button>
            </div>
          ) : (
            <TimeSeriesChart history={history.data} threshold={th} tail={tail} />
          )}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Wiring do app**

Substituir `src/App.tsx`:

```tsx
import { SensorDetailPage } from './pages/SensorDetailPage'
export default function App() {
  return <SensorDetailPage code="TEMP-EXP-01" />
}
```

Substituir `src/main.tsx`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import './index.css'

const qc = new QueryClient()
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
```

- [ ] **Step 6: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/pages/SensorDetailPage.test.tsx`
Expected: PASS — 2 testes.

- [ ] **Step 7: Suite completa + build**

Run: `cd frontend && npm test && npm run build`
Expected: todos os testes PASS; build sem erro.

- [ ] **Step 8: Verificação visual no browser**

Run: `cd frontend && npm run dev` — abrir, confirmar: readout atualizando ao vivo, ponto do trilho movendo, gráfico com cauda crescendo e linhas de limite, troca de janela, toggle claro/escuro.

- [ ] **Step 9: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add frontend/src/
git commit -m "feat(frontend): SensorDetailPage integrada + tema claro/escuro"
```

---

## Self-Review

**Spec coverage:**
- §2 stack → Task 1. §3 direção visual (tokens, readout, trilho, temas, mono) → Tasks 1,6,9. §4 seam adapters → Tasks 3,4. §5 contratos → Task 2 (CONTRACTS.md). §6 componentes → Tasks 6–9. §7 fluxo de dados → Tasks 4,5,9. §8 erro/reconexão → Task 9 (erro de histórico com retry; reconexão do liveApi fica na impl real, mock não cai). §9 testes 1–6 → Tasks 3,5,8,9,6. §10 entregáveis → todas.
- Gap consciente: §8 "reconexão do feed ao vivo / badge reconectando" não é exercido porque o mock não simula queda — anotado como fora do escopo desta fatia (entra com a impl SSE real). Skeletons de loading: parciais (texto "Carregando…"); refinamento visual fica para o polish.

**Placeholder scan:** sem TBD/TODO; todo passo tem código real.

**Type consistency:** `MetaApi/HistoryApi/LiveApi` consistentes entre `contracts.ts`, mocks e `index.ts`. `computeStatus`/`StatusResult` iguais em status.ts, ToleranceRail, LiveReadout. `buildChartOption(history, threshold)` mesma assinatura no teste e no componente. `useLiveTail(code, max)` idem.

**Nota de determinismo:** os mocks usam base de tempo fixa (`1_700_000_000_000`), sem `Date.now()`, para testes determinísticos — coerente com a restrição de ambiente.
