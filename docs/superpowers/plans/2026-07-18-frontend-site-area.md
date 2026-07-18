# Frontend Sentinela CME — Site → Área: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tela `/area/:areaCode` listando todos os sensores da área com valor ao vivo + status; `AreaCard` da Overview passa a linkar pra cá.

**Architecture:** Mock expande de 3 para 5 sensores (Expurgo e Preparo ganham um 2º sensor de pressão diferencial, valores reais do RDC15 já documentados em `odoo_modelo_dados_spec.md` §7). `AreaPage` reusa 100% da infraestrutura de dados já existente (`useSensors`/`useThresholds`/`useLiveStatuses`/`groupSensorsByArea` — desenhados desde a Overview pra N sensores/área). Único componente novo de UI: `SensorRow`, que reusa o vocabulário visual (`StatusIcon`/`statusTextColor`/`LABELS`) já estabelecido.

**Tech Stack:** Igual às fatias anteriores — Vite, React 19, TS, Tailwind v4, TanStack Query, react-router, Vitest + Testing Library.

## Global Constraints

- **Local:** `frontend/` dentro do worktree `/home/afonso/docker/odoo_sentinela/.worktrees/site-area` (branch `feat/frontend-site-area`). Não tocar nada fora deste worktree — checkout principal é compartilhado com outra sessão.
- **Sem seletor de site:** rota `/area/:areaCode`, sem `siteId` (mock de site único, consistente com o resto do app).
- **Thresholds de pressão são simplificação documentada:** a regra real (RDC15) é unilateral ("mais negativa que -2,5 Pa" / "mais positiva que +2,5 Pa"), sem teto rígido. Modelados como faixa `[-15, -2.5]` (Expurgo) e `[2.5, 15]` (Preparo) — o piso/teto extra (-15/15) é só um limite plausível de mock, não um valor regulatório. Documentar isso no código, não confundir com dado normativo real.
- **Nenhum elemento visual novo** além de `SensorRow` — reusa ícone/cor/label já existentes.
- TDD, commits frequentes.

---

## File Structure

```
frontend/src/
├── App.tsx                            # MODIFICA: + rota /area/:areaCode
├── App.test.tsx                       # MODIFICA: atualiza teste de clique (vai pra Area agora) + fluxo completo Overview->Area->Sensor->Voltar
├── components/
│   ├── AreaCard.tsx                   # MODIFICA: Link aponta pra /area/:code
│   ├── AreaCard.test.tsx              # MODIFICA: teste de href atualizado
│   ├── SensorRow.tsx                  # NOVO
│   └── SensorRow.test.tsx             # NOVO
├── pages/
│   ├── AreaPage.tsx                   # NOVO
│   └── AreaPage.test.tsx              # NOVO
└── lib/
    ├── queries.test.tsx               # MODIFICA: useSensors espera 5 sensores agora
    └── api/mock/
        ├── fixtures.ts                # MODIFICA: + PRESS-EXP-01, PRESS-PRE-01
        ├── historyApi.ts              # MODIFICA: usa threshold por sensor (nao mais so Expurgo)
        └── mock.test.ts               # MODIFICA: + testes dos 2 sensores novos, historyApi por sensor
```

---

### Task 1: Mock — 2 sensores de pressão diferencial + `historyApi` por sensor

**Files:**
- Modify: `frontend/src/lib/api/mock/fixtures.ts`
- Modify: `frontend/src/lib/api/mock/historyApi.ts`
- Modify: `frontend/src/lib/api/mock/mock.test.ts`
- Modify: `frontend/src/lib/queries.test.tsx`

**Interfaces:**
- Produces: `SENSORS` com 5 entradas; `THRESHOLDS` com os 2 novos códigos. `historyApi.getHistory(code, window)` passa a derivar a série do threshold **daquele** `code` (antes sempre usava o threshold fixo de Expurgo, independente do sensor pedido — simplificação pré-existente, corrigida aqui porque os novos sensores de pressão tornariam isso visivelmente errado: gráfico de pressão mostrando forma/limites de temperatura).

- [ ] **Step 1: Escrever testes (falha)**

Em `frontend/src/lib/api/mock/mock.test.ts`, substituir o teste `'listSensors devolve os 3 sensores...'` por:

```ts
  it('listSensors devolve os 5 sensores (2 areas ganham sensor de pressao)', async () => {
    const sensors = await mockMetaApi.listSensors()
    const codes = sensors.map((s) => s.sensor_code).sort()
    expect(codes).toEqual(['PRESS-EXP-01', 'PRESS-PRE-01', 'TEMP-ARS-01', 'TEMP-EXP-01', 'TEMP-PRE-01'])
  })
```

Adicionar ao final do `describe('mockMetaApi', ...)`:

```ts
  it('Expurgo pressao: negativa, faixa [-15, -2.5]', async () => {
    const t = await mockMetaApi.getThreshold('PRESS-EXP-01')
    expect(t).toEqual({ sensor_id: 'PRESS-EXP-01', limite_min: -15, limite_max: -2.5, is_valor_padrao_regulatorio: true })
  })
  it('Preparo pressao: positiva, faixa [2.5, 15]', async () => {
    const t = await mockMetaApi.getThreshold('PRESS-PRE-01')
    expect(t).toEqual({ sensor_id: 'PRESS-PRE-01', limite_min: 2.5, limite_max: 15, is_valor_padrao_regulatorio: true })
  })
```

Adicionar ao final do `describe('mockHistoryApi', ...)`:

```ts
  it('serie deriva do threshold do sensor pedido, nao sempre de Expurgo', async () => {
    const pressao = await mockHistoryApi.getHistory('PRESS-EXP-01', '1h')
    const valores = pressao.points.map((p) => ('value' in p ? p.value : p.avg))
    // faixa de pressao Expurgo e negativa [-15,-2.5] — toda a serie deve estar
    // na vizinhanca negativa, bem longe da faixa de temperatura (positiva, ~20).
    expect(Math.max(...valores)).toBeLessThan(0)
  })
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/lib/api/mock/mock.test.ts`
Expected: FAIL — sensores novos não existem; `historyApi` ainda ignora o `code`.

- [ ] **Step 3: Adicionar os 2 sensores em `fixtures.ts`**

Em `frontend/src/lib/api/mock/fixtures.ts`, adicionar antes da linha `export const SENSORS: SensorMeta[] = ...`:

```ts
// Pressao diferencial: valores reais de referencia RDC15 ja documentados em
// odoo_modelo_dados_spec.md §7 (Expurgo negativa min 2,5 Pa; Preparo positiva
// min 2,5 Pa). A regra real e unilateral ("mais negativa/positiva que X"),
// sem teto rigido documentado — o piso/teto extra abaixo (-15/15) e so um
// limite plausivel de mock p/ desenhar uma faixa, NAO e valor regulatorio.
const SENSOR_PRESSAO_EXP: SensorMeta = {
  sensor_code: 'PRESS-EXP-01',
  name: 'Pressão diferencial — Expurgo',
  unidade: 'Pa',
  protocolo_origem: 'rs485',
  measurement_type: { code: 'pressao_diferencial', name: 'Pressão diferencial' },
  area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Descontaminação' },
}

const THRESHOLD_PRESSAO_EXP: Threshold = {
  sensor_id: 'PRESS-EXP-01',
  limite_min: -15,
  limite_max: -2.5,
  is_valor_padrao_regulatorio: true,
}

const SENSOR_PRESSAO_PRE: SensorMeta = {
  sensor_code: 'PRESS-PRE-01',
  name: 'Pressão diferencial — Preparo/Esterilização',
  unidade: 'Pa',
  protocolo_origem: 'rs485',
  measurement_type: { code: 'pressao_diferencial', name: 'Pressão diferencial' },
  area: { area_code: 'PREPARO_ESTER', name: 'Preparo/Esterilização', category: 'Esterilização' },
}

const THRESHOLD_PRESSAO_PRE: Threshold = {
  sensor_id: 'PRESS-PRE-01',
  limite_min: 2.5,
  limite_max: 15,
  is_valor_padrao_regulatorio: true,
}
```

E atualizar as duas exportações finais do arquivo:

```ts
export const SENSORS: SensorMeta[] = [SENSOR, SENSOR_PREPARO, SENSOR_ARSENAL, SENSOR_PRESSAO_EXP, SENSOR_PRESSAO_PRE]

export const THRESHOLDS: Record<string, Threshold | null> = {
  [SENSOR.sensor_code]: THRESHOLD,
  [SENSOR_PREPARO.sensor_code]: THRESHOLD_PREPARO,
  [SENSOR_ARSENAL.sensor_code]: null,
  [SENSOR_PRESSAO_EXP.sensor_code]: THRESHOLD_PRESSAO_EXP,
  [SENSOR_PRESSAO_PRE.sensor_code]: THRESHOLD_PRESSAO_PRE,
}
```

(`liveApi.ts` não precisa de nenhuma entrada nova em `AMP_FRACTION` — os sensores de pressão caem no `DEFAULT_AMP_FRACTION` já existente, o que os mantém confortavelmente dentro da faixa, comportamento aceitável e não testado explicitamente por este plano.)

- [ ] **Step 4: Corrigir `historyApi.ts` — série deriva do threshold do sensor pedido**

Substituir `frontend/src/lib/api/mock/historyApi.ts`:

```ts
import type { HistoryApi } from '../contracts'
import type { HistoryResponse, HistoryPoint, Window, Threshold } from '../../types'
import { THRESHOLD, THRESHOLDS } from './fixtures'

const SPAN_MS: Record<Window, number> = {
  '1h': 3_600_000, '24h': 86_400_000, '7d': 604_800_000, '30d': 2_592_000_000,
}

// Série sintética determinística (senoide em torno do meio da faixa do
// threshold DO SENSOR PEDIDO + ruído fixo). Sensor sem threshold (Arsenal) ou
// código desconhecido cai no fallback do threshold de Expurgo — só para ter
// uma faixa plausível de plotar, sem significado regulatório.
function synth(window: Window, threshold: Threshold): { resolution: 'raw' | 'agg'; points: HistoryPoint[] } {
  const span = SPAN_MS[window]
  const now = 1_700_000_000_000 // base fixa (sem Date.now — determinístico p/ teste)
  const mid = (threshold.limite_min + threshold.limite_max) / 2
  const amp = (threshold.limite_max - threshold.limite_min) / 3
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
    const threshold = THRESHOLDS[sensor_code] ?? THRESHOLD
    const { resolution, points } = synth(window, threshold)
    return { sensor_code, window, resolution, points }
  },
}
```

- [ ] **Step 5: Atualizar `queries.test.tsx` — `useSensors` agora espera 5 sensores**

Em `frontend/src/lib/queries.test.tsx`, trocar o teste `'useSensors lista os 3 sensores'`:

```tsx
  it('useSensors lista os 5 sensores', async () => {
    const { result } = renderHook(() => useSensors(), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.map((s) => s.sensor_code).sort()).toEqual([
      'PRESS-EXP-01', 'PRESS-PRE-01', 'TEMP-ARS-01', 'TEMP-EXP-01', 'TEMP-PRE-01',
    ])
  })
```

- [ ] **Step 6: Rodar testes (devem passar) + suite completa**

Run: `cd frontend && npx vitest run src/lib/api/mock/mock.test.ts src/lib/queries.test.tsx`
Expected: PASS — todos.

Run: `cd frontend && npm test`
Expected: PASS — suite completa. `OverviewPage.test.tsx` continua verde: o teste `'Arsenal mostra "Sem limite"'` conta ocorrências de "Sem limite" **por cartão de área** (3 áreas, não 5 sensores) — Expurgo/Preparo têm agora 2 sensores cada, mas ambos com threshold configurado, então o agregado da área nunca vira "Sem limite" por causa disso; só Arsenal continua sem threshold. Se este teste falhar, investigar antes de prosseguir — não é esperado.

- [ ] **Step 7: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela/.worktrees/site-area
git add frontend/src/lib/api/mock/fixtures.ts frontend/src/lib/api/mock/historyApi.ts frontend/src/lib/api/mock/mock.test.ts frontend/src/lib/queries.test.tsx
git commit -m "feat(frontend): mock ganha sensores de pressao diferencial (Expurgo/Preparo) + historyApi por sensor"
```

---

### Task 2: `SensorRow`

**Files:**
- Create: `frontend/src/components/SensorRow.tsx`
- Create: `frontend/src/components/SensorRow.test.tsx`

**Interfaces:**
- Consumes: `sensorDisplayState` (`lib/aggregateStatus.ts`), `StatusIcon`/`statusTextColor` (`components/statusVisuals.tsx`), `LABELS` (`lib/status.ts`).
- Produces: `<SensorRow sensor={SensorMeta} threshold={Threshold|null} live={LivePoint|undefined} />` — linha clicável (`Link` pro Detalhe do Sensor), nome do tipo de medição, valor+unidade, status (ícone+cor+texto).

- [ ] **Step 1: Escrever testes (falha)**

`frontend/src/components/SensorRow.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { SensorRow } from './SensorRow'
import type { LivePoint, SensorMeta, Threshold } from '../lib/types'

function wrap(node: React.ReactNode) {
  return <MemoryRouter>{node}</MemoryRouter>
}

const sensor: SensorMeta = {
  sensor_code: 'PRESS-EXP-01',
  name: 'Pressão diferencial — Expurgo',
  unidade: 'Pa',
  protocolo_origem: 'rs485',
  measurement_type: { code: 'pressao_diferencial', name: 'Pressão diferencial' },
  area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Descontaminação' },
}
const t: Threshold = { sensor_id: 'PRESS-EXP-01', limite_min: -15, limite_max: -2.5, is_valor_padrao_regulatorio: true }

describe('SensorRow', () => {
  it('mostra tipo de medicao, valor+unidade, e e um link pro sensor', () => {
    const live: LivePoint = { sensor_code: 'PRESS-EXP-01', ts: 1, value: -5.2, alarm_state: 'ok' }
    render(wrap(<SensorRow sensor={sensor} threshold={t} live={live} />))
    expect(screen.getByText('Pressão diferencial')).toBeInTheDocument()
    expect(screen.getByText('-5.2')).toBeInTheDocument()
    expect(screen.getByText('Pa')).toBeInTheDocument()
    expect(screen.getByRole('link')).toHaveAttribute('href', '/sensor/PRESS-EXP-01')
  })

  it('status sempre com icone (nao so cor) + texto', () => {
    const live: LivePoint = { sensor_code: 'PRESS-EXP-01', ts: 1, value: -5.2, alarm_state: 'ok' }
    const { container } = render(wrap(<SensorRow sensor={sensor} threshold={t} live={live} />))
    expect(screen.getByText('Dentro da faixa')).toBeInTheDocument()
    expect(container.querySelector('svg')).not.toBeNull()
  })

  it('sem dado ao vivo ainda: mostra placeholder no valor', () => {
    render(wrap(<SensorRow sensor={sensor} threshold={t} live={undefined} />))
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/components/SensorRow.test.tsx`
Expected: FAIL — `./SensorRow` não existe.

- [ ] **Step 3: Implementar**

`frontend/src/components/SensorRow.tsx`:

```tsx
import { Link } from 'react-router'
import { LABELS } from '../lib/status'
import { sensorDisplayState } from '../lib/aggregateStatus'
import { StatusIcon, statusTextColor } from './statusVisuals'
import type { LivePoint, SensorMeta, Threshold } from '../lib/types'

export function SensorRow({
  sensor,
  threshold,
  live,
}: {
  sensor: SensorMeta
  threshold: Threshold | null
  live: LivePoint | undefined
}) {
  const state = sensorDisplayState(threshold, live)

  return (
    <Link
      to={`/sensor/${sensor.sensor_code}`}
      className="flex items-center justify-between gap-4 rounded-xl border border-[var(--color-line)] p-4 outline-none transition-colors duration-200 ease-out hover:border-[var(--color-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
      style={{ background: 'var(--color-surface)' }}
    >
      <div>
        <p className="text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>
          {sensor.measurement_type.name}
        </p>
        <div
          className="mt-1 flex items-center gap-2 text-xs font-semibold"
          style={{ color: statusTextColor(state) }}
        >
          <StatusIcon state={state} />
          <span>{LABELS[state]}</span>
        </div>
      </div>

      <span className="font-mono text-lg font-semibold tabular-nums" style={{ color: 'var(--color-ink)' }}>
        {live ? live.value.toFixed(1) : '—'}{' '}
        <span className="text-sm font-medium" style={{ color: 'var(--color-muted)' }}>
          {sensor.unidade}
        </span>
      </span>
    </Link>
  )
}
```

- [ ] **Step 4: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/components/SensorRow.test.tsx`
Expected: PASS — todos os 3.

- [ ] **Step 5: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela/.worktrees/site-area
git add frontend/src/components/SensorRow.tsx frontend/src/components/SensorRow.test.tsx
git commit -m "feat(frontend): SensorRow — linha de sensor c/ valor ao vivo e status"
```

---

### Task 3: `AreaPage` + rota `/area/:areaCode`

**Files:**
- Create: `frontend/src/pages/AreaPage.tsx`
- Create: `frontend/src/pages/AreaPage.test.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `useSensors`, `useThresholds` (`lib/queries.ts`), `useLiveStatuses` (`lib/useLiveStatuses.ts`), `groupSensorsByArea` (`lib/aggregateStatus.ts`), `SensorRow` (Task 2).
- Produces: `<AreaPage />` (lê `areaCode` via `useParams`). Rota `/area/:areaCode` em `App.tsx`.

- [ ] **Step 1: Escrever testes (falha)**

`frontend/src/pages/AreaPage.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router'
import type { ReactNode } from 'react'

import { AreaPage } from './AreaPage'

function wrap(node: ReactNode, initialPath: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/area/:areaCode" element={node} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('AreaPage', () => {
  it('lista os 2 sensores do Expurgo (temperatura + pressao)', async () => {
    render(wrap(<AreaPage />, '/area/EXPURGO'))
    await waitFor(() => expect(screen.getByText('Temperatura')).toBeInTheDocument(), { timeout: 3000 })
    expect(screen.getByText('Pressão diferencial')).toBeInTheDocument()
  })

  it('area inexistente mostra mensagem, nao quebra', async () => {
    render(wrap(<AreaPage />, '/area/NAO-EXISTE'))
    await waitFor(() => expect(screen.getByText(/não encontrada/i)).toBeInTheDocument(), { timeout: 3000 })
  })

  it('Arsenal (1 sensor, sem threshold) mostra Sem limite', async () => {
    render(wrap(<AreaPage />, '/area/ARSENAL'))
    await waitFor(() => expect(screen.getByText('Sem limite')).toBeInTheDocument(), { timeout: 3000 })
  })
})
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/pages/AreaPage.test.tsx`
Expected: FAIL — `./AreaPage` não existe.

- [ ] **Step 3: Implementar `AreaPage.tsx`**

`frontend/src/pages/AreaPage.tsx`:

```tsx
import { useParams, Link } from 'react-router'
import { useSensors, useThresholds } from '../lib/queries'
import { useLiveStatuses } from '../lib/useLiveStatuses'
import { groupSensorsByArea } from '../lib/aggregateStatus'
import { SensorRow } from '../components/SensorRow'

function SkeletonRow() {
  return (
    <div
      className="h-16 animate-pulse rounded-xl motion-reduce:animate-none"
      style={{ background: 'var(--color-line)' }}
      aria-hidden="true"
    />
  )
}

export function AreaPage() {
  const { areaCode } = useParams<{ areaCode: string }>()
  const sensorsQuery = useSensors()
  const sensors = sensorsQuery.data ?? []
  const codes = sensors.map((s) => s.sensor_code)
  const thresholdResults = useThresholds(codes)
  const thresholdsByCode = Object.fromEntries(codes.map((c, i) => [c, thresholdResults[i]?.data]))
  const liveByCode = useLiveStatuses(codes)
  const groups = groupSensorsByArea(sensors)
  const group = groups.find((g) => g.area.area_code === areaCode)
  const ready =
    sensorsQuery.isSuccess &&
    thresholdResults.every((r) => r.isSuccess) &&
    codes.every((c) => liveByCode[c] !== undefined)

  return (
    <div className="mx-auto max-w-3xl p-4 sm:p-6">
      <Link
        to="/"
        className="mb-2 inline-flex items-center gap-1 text-sm font-medium text-[var(--color-muted)] outline-none transition-colors duration-200 ease-out hover:text-[var(--color-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
      >
        ← Voltar
      </Link>

      {sensorsQuery.isError ? (
        <div
          className="flex h-40 flex-col items-center justify-center gap-2 text-center text-sm"
          style={{ color: 'var(--color-crit)' }}
        >
          <span>Falha ao carregar os sensores.</span>
          <button
            type="button"
            className="min-h-11 rounded-md px-3 font-semibold underline outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
            onClick={() => sensorsQuery.refetch()}
          >
            Tentar de novo
          </button>
        </div>
      ) : !ready ? (
        <div className="mt-4 space-y-3">
          <SkeletonRow />
          <SkeletonRow />
        </div>
      ) : !group ? (
        <p className="mt-4 text-sm" style={{ color: 'var(--color-muted)' }}>
          Área não encontrada.
        </p>
      ) : (
        <>
          <header className="mb-6 mt-2">
            <h1 className="text-xl font-bold" style={{ color: 'var(--color-ink)' }}>
              {group.area.name}
            </h1>
            <p className="mt-1 text-sm" style={{ color: 'var(--color-muted)' }}>
              {group.area.category}
            </p>
          </header>
          <div className="space-y-3">
            {group.sensors.map((s) => (
              <SensorRow
                key={s.sensor_code}
                sensor={s}
                threshold={thresholdsByCode[s.sensor_code] ?? null}
                live={liveByCode[s.sensor_code]}
              />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Adicionar a rota em `App.tsx`**

Em `frontend/src/App.tsx`, adicionar o import e a rota:

```tsx
import { Routes, Route, useParams } from 'react-router'
import { OverviewPage } from './pages/OverviewPage'
import { SensorDetailPage } from './pages/SensorDetailPage'
import { AreaPage } from './pages/AreaPage'

function SensorRoute() {
  const { code } = useParams<{ code: string }>()
  return <SensorDetailPage code={code!} />
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<OverviewPage />} />
      <Route path="/area/:areaCode" element={<AreaPage />} />
      <Route path="/sensor/:code" element={<SensorRoute />} />
    </Routes>
  )
}
```

- [ ] **Step 5: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/pages/AreaPage.test.tsx`
Expected: PASS — todos os 3.

Run: `cd frontend && npm test`
Expected: PASS — suite completa.

- [ ] **Step 6: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela/.worktrees/site-area
git add frontend/src/pages/AreaPage.tsx frontend/src/pages/AreaPage.test.tsx frontend/src/App.tsx
git commit -m "feat(frontend): AreaPage + rota /area/:areaCode"
```

---

### Task 4: `AreaCard` relinka pra `/area/:code` + fluxo de navegação completo

**Files:**
- Modify: `frontend/src/components/AreaCard.tsx`
- Modify: `frontend/src/components/AreaCard.test.tsx`
- Modify: `frontend/src/App.test.tsx`

**Interfaces:**
- Produces: `AreaCard` linka pra `/area/${group.area.area_code}` (antes: `/sensor/${group.sensors[0].sensor_code}`).

- [ ] **Step 1: Atualizar `AreaCard.test.tsx` — teste de href**

Em `frontend/src/components/AreaCard.test.tsx`, trocar o teste `'e um link pro sensor da area'`:

```tsx
  it('e um link pra pagina da area', () => {
    render(wrap(<AreaCard group={expurgo} thresholdsByCode={{ 'TEMP-EXP-01': t }} liveByCode={{}} />))
    expect(screen.getByRole('link')).toHaveAttribute('href', '/area/EXPURGO')
  })
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/components/AreaCard.test.tsx`
Expected: FAIL — `href` ainda aponta pro sensor.

- [ ] **Step 3: Implementar — trocar o `to` do `Link`**

Em `frontend/src/components/AreaCard.tsx`, trocar:

```tsx
      to={`/sensor/${group.sensors[0].sensor_code}`}
```

por:

```tsx
      to={`/area/${group.area.area_code}`}
```

- [ ] **Step 4: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/components/AreaCard.test.tsx`
Expected: PASS — todos.

- [ ] **Step 5: Atualizar `App.test.tsx` — fluxo de navegação completo**

Em `frontend/src/App.test.tsx`, substituir o teste `'clicar num cartao da Overview navega pro Detalhe, e Voltar retorna'` por:

```tsx
  it('fluxo completo: Overview -> Area -> Sensor -> Voltar -> Area', async () => {
    render(wrap(<App />, '/'))
    await waitFor(() => expect(screen.getByText('Expurgo')).toBeInTheDocument(), { timeout: 3000 })

    await userEvent.click(screen.getByTestId('area-card-EXPURGO'))
    await waitFor(() => expect(screen.getByText('Pressão diferencial')).toBeInTheDocument(), { timeout: 3000 })

    await userEvent.click(screen.getByText('Temperatura'))
    await waitFor(() => expect(screen.getByText(/Temperatura — Expurgo/)).toBeInTheDocument())

    await userEvent.click(screen.getByRole('link', { name: /voltar/i }))
    await waitFor(() => expect(screen.getByText('Pressão diferencial')).toBeInTheDocument(), { timeout: 3000 })
  })
```

Nota: o "Voltar" do Detalhe do Sensor leva pra `/` (não pra `/area/:code`) — comportamento já existente da fatia de Roteamento, não mudou nesta fatia. Este teste verifica isso explicitamente: depois do "Voltar" a asserção espera o conteúdo da **Area** page reaparecer — o que só funciona se, na verdade, o "Voltar" do Detalhe volta pra Overview e dali navegamos de novo? **Corrigir**: o link "Voltar" do `SensorDetailPage` aponta pra `/` (Overview), não pra área. Ajustar a última asserção do teste acima para refletir isso:

```tsx
    await userEvent.click(screen.getByRole('link', { name: /voltar/i }))
    await waitFor(() => expect(screen.getByText('Visão geral')).toBeInTheDocument(), { timeout: 3000 })
```

(Melhorar a navegação de volta pro Detalhe do Sensor lembrar de qual área veio é um refinamento de UX fora do escopo desta fatia — candidato futuro, não bloqueia.)

- [ ] **Step 6: Rodar teste (deve passar) + suite completa + build**

Run: `cd frontend && npx vitest run src/App.test.tsx`
Expected: PASS.

Run: `cd frontend && npm test`
Expected: PASS — suite completa.

Run: `cd frontend && npm run build`
Expected: build limpo.

- [ ] **Step 7: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela/.worktrees/site-area
git add frontend/src/components/AreaCard.tsx frontend/src/components/AreaCard.test.tsx frontend/src/App.test.tsx
git commit -m "feat(frontend): AreaCard linka pra /area/:code; fluxo de navegacao completo testado"
```

---

## Self-Review

**Spec coverage:** §2 mock (2 sensores de pressão) → Task 1. §3 rota → Task 3. §4 navegação (AreaCard relink, Voltar, linha→Detalhe) → Tasks 3, 4. §5 dados (reuso) → Task 3 (nenhuma peça nova de infra). §6 componentes (`AreaPage`/`SensorRow`) → Tasks 2, 3. §7 erro/loading/área-inexistente → Task 3. §8 testes 1-5 → Task 1 (1), Task 2 (2), Task 3 (3), Task 4 (4, 5).

**Placeholder scan:** sem TBD/TODO; todo passo tem código completo.

**Type consistency:** `SensorRow` recebe exatamente `{sensor: SensorMeta, threshold: Threshold|null, live: LivePoint|undefined}`, mesmo padrão de props opcionais/nulos já usado em `AreaCard`. `groupSensorsByArea`/`AreaGroup` reusados sem alteração de assinatura.

**Risco assumido e documentado:** o link "Voltar" do Detalhe do Sensor sempre volta pra Overview (`/`), não pra área de origem — mesmo quando o usuário chegou lá via `AreaPage`. Documentado explicitamente no Task 4 como refinamento futuro, não um bug desta fatia (o comportamento já existia da fatia de Roteamento; não piora nem melhora aqui).

**Nota sobre verificação visual:** as 3 fatias anteriores acharam bugs reais só visíveis no browser real (gráfico vazio, cor errada, hover morto) — repetir a mesma disciplina aqui é obrigatório antes de considerar a fatia pronta, mesmo com suite 100% verde.
