# Frontend Sentinela CME — Overview: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir a tela Overview (visão do cliente) — cartões por área com estado agregado + contagem de alarmes ativos — contra mocks expandidos para múltiplos sensores.

**Architecture:** Expande o mock de 1 sensor fixo para 3 (1 por área: Expurgo/Preparo-Esterilização/Arsenal), reusando o seam mock→real e a direção visual "instrumento calibrado" já estabelecidos no slice anterior (Detalhe do Sensor). `OverviewPage` compõe `useSensors` + `useThresholds` (TanStack Query) + `useLiveStatuses` (novo hook, análogo a `useLiveTail` mas sem buffer — só o último valor por sensor) → agrupa por área (`groupSensorsByArea`) → agrega estado (`worstAlarmState`) → renderiza `AreaCard`.

**Tech Stack:** Igual ao slice anterior — Vite, React 18, TypeScript, Tailwind v4, TanStack Query v5 (incluindo `useQueries`), Vitest + Testing Library.

## Global Constraints

- **Local:** `frontend/` (projeto existente, não recriar scaffold).
- **Escopo:** só visão do cliente (1 site). Sem operador SaaS multi-cliente nesta fatia.
- **Sem roteamento:** clicar num cartão não navega. `App.tsx` passa a renderizar `OverviewPage` (Overview vira a tela raiz; `SensorDetailPage` continua existindo/testada, só fica temporariamente inalcançável pela UI).
- **Contagem de "alarme ativo"** = só sensores em `crit` (nunca `warn` — alinhado ao modelo real, `alarm.event` só nasce de violação de limite).
- **Estado de um sensor sem threshold configurado é sempre `unknown`** ("Sem limite"), mesmo que o feed ao vivo internamente reporte `alarm_state: 'ok'` (convenção existente do `liveApi`: `'unknown' → 'ok'` na emissão, porque `LivePoint.alarm_state` não tem variante `'unknown'`). A UI reconstrói essa distinção a partir do `threshold`, não do `alarm_state` bruto — usar `sensorDisplayState(threshold, live)`, nunca `live.alarm_state` diretamente para decidir "tem limite ou não".
- **Compatibilidade:** `TEMP-EXP-01` continua funcionando exatamente como antes. Testes pré-existentes que chamavam `getSensor('x')`/`getThreshold('x')`/`useSensorMeta('x')`/`useThreshold('x')` com o código genérico `'x'` (válido antes porque o mock ignorava o parâmetro) devem ser atualizados para `'TEMP-EXP-01'` — mudança de comportamento deliberada e anunciada no design (`docs/superpowers/specs/2026-07-18-frontend-overview-design.md` §2), não uma regressão a evitar.
- **Reuso da direção visual:** cor sempre + ícone + texto (nunca só cor); tokens OKLCH existentes (`--color-good/warn/crit/muted/ink/surface/line/panel/primary`); `LABELS`/`WARN_MARGIN` de `lib/status.ts` (já exportados, não duplicar).
- **TDD**, commits frequentes.

---

## File Structure

```
frontend/src/
├── lib/
│   ├── aggregateStatus.ts          # NOVO: sensorDisplayState, worstAlarmState, groupSensorsByArea, AreaGroup
│   ├── aggregateStatus.test.ts     # NOVO
│   ├── useLiveStatuses.ts          # NOVO: hook multi-sensor (análogo a useLiveTail, sem buffer)
│   ├── useLiveStatuses.test.tsx    # NOVO
│   ├── queries.ts                  # MODIFICA: + useSensors, useThresholds
│   ├── queries.test.tsx            # MODIFICA: + testes novos, corrige 'x'→'TEMP-EXP-01'
│   └── api/
│       ├── contracts.ts            # MODIFICA: MetaApi + listSensors
│       └── mock/
│           ├── fixtures.ts         # MODIFICA: + SENSOR_PREPARO/ARSENAL, SENSORS[], THRESHOLDS
│           ├── metaApi.ts          # MODIFICA: lookup por code real
│           ├── liveApi.ts          # MODIFICA: parametriza por sensor
│           └── mock.test.ts        # MODIFICA: + testes novos, corrige 'x'→'TEMP-EXP-01' (metaApi)
├── components/
│   ├── statusVisuals.tsx           # NOVO: StatusIcon + statusTextColor (extraído de LiveReadout)
│   ├── LiveReadout.tsx             # MODIFICA: refatora para usar statusVisuals (sem mudar comportamento)
│   ├── AreaCard.tsx                # NOVO
│   └── AreaCard.test.tsx           # NOVO
├── pages/
│   ├── OverviewPage.tsx            # NOVO
│   └── OverviewPage.test.tsx       # NOVO
└── App.tsx                         # MODIFICA: renderiza OverviewPage
```

---

### Task 1: Expandir fixtures + `metaApi.listSensors` + lookup por código real

**Files:**
- Modify: `frontend/src/lib/api/contracts.ts`
- Modify: `frontend/src/lib/api/mock/fixtures.ts`
- Modify: `frontend/src/lib/api/mock/metaApi.ts`
- Modify: `frontend/src/lib/api/mock/mock.test.ts` (testes de `mockMetaApi`)
- Modify: `frontend/src/lib/queries.test.tsx` (corrige `'x'` → `'TEMP-EXP-01'` nos 2 testes afetados)

**Interfaces:**
- Produces: `MetaApi.listSensors(): Promise<SensorMeta[]>`. `SENSORS: SensorMeta[]` e `THRESHOLDS: Record<string, Threshold | null>` exportados de `fixtures.ts`. `getSensor(code)` lança erro para código desconhecido; `getThreshold(code)` devolve `null` para sensor sem threshold (Arsenal) e lança erro para código desconhecido.

- [ ] **Step 1: Escrever testes (falha) em `mock.test.ts` — substituir o bloco `describe('mockMetaApi', ...)` existente**

Abrir `frontend/src/lib/api/mock/mock.test.ts` e substituir só o bloco:

```ts
describe('mockMetaApi', () => {
  it('devolve sensor e threshold da fixture', async () => {
    expect((await mockMetaApi.getSensor('x')).sensor_code).toBe('TEMP-EXP-01')
    expect((await mockMetaApi.getThreshold('x'))?.limite_max).toBe(22)
  })
})
```

por:

```ts
describe('mockMetaApi', () => {
  it('getSensor/getThreshold buscam pelo codigo real (TEMP-EXP-01, ja existente)', async () => {
    expect((await mockMetaApi.getSensor('TEMP-EXP-01')).sensor_code).toBe('TEMP-EXP-01')
    expect((await mockMetaApi.getThreshold('TEMP-EXP-01'))?.limite_max).toBe(22)
  })
  it('listSensors devolve os 3 sensores (Expurgo, Preparo/Esterilizacao, Arsenal)', async () => {
    const sensors = await mockMetaApi.listSensors()
    const codes = sensors.map((s) => s.sensor_code).sort()
    expect(codes).toEqual(['TEMP-ARS-01', 'TEMP-EXP-01', 'TEMP-PRE-01'])
  })
  it('Preparo/Esterilizacao tem threshold 20-24', async () => {
    const t = await mockMetaApi.getThreshold('TEMP-PRE-01')
    expect(t).toEqual({ sensor_id: 'TEMP-PRE-01', limite_min: 20, limite_max: 24, is_valor_padrao_regulatorio: true })
  })
  it('Arsenal nao tem threshold (null, sem lancar erro)', async () => {
    const sensor = await mockMetaApi.getSensor('TEMP-ARS-01')
    expect(sensor.area.name).toBe('Arsenal')
    expect(await mockMetaApi.getThreshold('TEMP-ARS-01')).toBeNull()
  })
  it('codigo desconhecido lanca erro em getSensor e getThreshold', async () => {
    await expect(mockMetaApi.getSensor('NAO-EXISTE')).rejects.toThrow()
    await expect(mockMetaApi.getThreshold('NAO-EXISTE')).rejects.toThrow()
  })
})
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/lib/api/mock/mock.test.ts`
Expected: FAIL — `listSensors` não existe em `mockMetaApi`; `getSensor('x')`/`getThreshold('x')` (se algum teste antigo restar) ou os novos testes com códigos reais falham porque `metaApi.ts` ainda ignora o parâmetro `code`.

- [ ] **Step 3: Estender `contracts.ts`**

Em `frontend/src/lib/api/contracts.ts`, alterar o tipo `MetaApi`:

```ts
export type MetaApi = {
  getSensor(code: string): Promise<SensorMeta>
  getThreshold(code: string): Promise<Threshold | null>
  listSensors(): Promise<SensorMeta[]>
}
```

- [ ] **Step 4: Estender `fixtures.ts`**

Substituir o conteúdo de `frontend/src/lib/api/mock/fixtures.ts` por:

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

const SENSOR_PREPARO: SensorMeta = {
  sensor_code: 'TEMP-PRE-01',
  name: 'Temperatura — Preparo/Esterilização',
  unidade: 'C',
  protocolo_origem: 'rs485',
  measurement_type: { code: 'temperatura', name: 'Temperatura' },
  area: { area_code: 'PREPARO_ESTER', name: 'Preparo/Esterilização', category: 'Preparo/Esterilização' },
}

const THRESHOLD_PREPARO: Threshold = {
  sensor_id: 'TEMP-PRE-01',
  limite_min: 20,
  limite_max: 24,
  is_valor_padrao_regulatorio: true,
}

const SENSOR_ARSENAL: SensorMeta = {
  sensor_code: 'TEMP-ARS-01',
  name: 'Temperatura — Arsenal',
  unidade: 'C',
  protocolo_origem: 'rs485',
  measurement_type: { code: 'temperatura', name: 'Temperatura' },
  area: { area_code: 'ARSENAL', name: 'Arsenal', category: 'Arsenal' },
}

// Arsenal nao tem threshold regulatorio definido em odoo_modelo_dados_spec.md §7
// (so Expurgo e Preparo/Esterilizacao tem defaults RDC 15) — deliberadamente sem
// limite, exercita o estado "sem limite" do ThresholdBadge/computeStatus/AreaCard.
export const SENSORS: SensorMeta[] = [SENSOR, SENSOR_PREPARO, SENSOR_ARSENAL]

export const THRESHOLDS: Record<string, Threshold | null> = {
  [SENSOR.sensor_code]: THRESHOLD,
  [SENSOR_PREPARO.sensor_code]: THRESHOLD_PREPARO,
  [SENSOR_ARSENAL.sensor_code]: null,
}
```

- [ ] **Step 5: Reescrever `metaApi.ts` com lookup real por código**

Substituir `frontend/src/lib/api/mock/metaApi.ts`:

```ts
import type { MetaApi } from '../contracts'
import { SENSORS, THRESHOLDS } from './fixtures'

export const mockMetaApi: MetaApi = {
  async getSensor(code) {
    const found = SENSORS.find((s) => s.sensor_code === code)
    if (!found) throw new Error(`sensor nao encontrado: ${code}`)
    return found
  },
  async getThreshold(code) {
    if (!(code in THRESHOLDS)) throw new Error(`sensor nao encontrado: ${code}`)
    return THRESHOLDS[code]
  },
  async listSensors() {
    return SENSORS
  },
}
```

- [ ] **Step 6: Corrigir os 2 testes de `queries.test.tsx` que usavam código genérico `'x'`**

Em `frontend/src/lib/queries.test.tsx`, trocar `'x'` por `'TEMP-EXP-01'` só nestes dois testes (deixar `useHistory('x', '1h')` como está — `historyApi` não muda nesta task):

```tsx
  it('useSensorMeta carrega a fixture', async () => {
    const { result } = renderHook(() => useSensorMeta('TEMP-EXP-01'), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.sensor_code).toBe('TEMP-EXP-01')
  })
```

```tsx
  it('useThreshold carrega limites', async () => {
    const { result } = renderHook(() => useThreshold('TEMP-EXP-01'), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.limite_max).toBe(22)
  })
```

- [ ] **Step 7: Rodar testes (devem passar) — arquivos afetados + suite completa**

Run: `cd frontend && npx vitest run src/lib/api/mock/mock.test.ts src/lib/queries.test.tsx`
Expected: PASS — todos.

Run: `cd frontend && npm test`
Expected: PASS — suite completa (nenhuma regressão em `SensorDetailPage.test.tsx`, `useLiveTail.test.tsx` etc., que usam `TEMP-EXP-01` real ou não passam por `metaApi`).

- [ ] **Step 8: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add frontend/src/lib/api/contracts.ts frontend/src/lib/api/mock/fixtures.ts frontend/src/lib/api/mock/metaApi.ts frontend/src/lib/api/mock/mock.test.ts frontend/src/lib/queries.test.tsx
git commit -m "feat(frontend): expande fixtures p/ 3 sensores + metaApi.listSensors + lookup por codigo real"
```

---

### Task 2: `liveApi` parametrizado por sensor

**Files:**
- Modify: `frontend/src/lib/api/mock/liveApi.ts`
- Modify: `frontend/src/lib/api/mock/mock.test.ts` (adiciona testes ao bloco `describe('mockLiveApi', ...)`, existente permanece)

**Interfaces:**
- Consumes: `THRESHOLDS` (de `fixtures.ts`, Task 1), `computeStatus` (`lib/status.ts`).
- Produces: `mockLiveApi.subscribe(code, cb)` — onda sintética com ponto médio/amplitude derivados do threshold do `code` recebido (Expurgo: comportamento **idêntico** ao atual; Preparo: amplitude maior, cruza a faixa periodicamente — produz `alarm_state: 'crit'` às vezes, propositalmente, para a Overview ter o que mostrar na contagem de alarmes; Arsenal: sem threshold, ponto médio/amplitude fixos, `alarm_state` sempre `'ok'`).

- [ ] **Step 1: Adicionar testes (falha) ao final do `describe('mockLiveApi', ...)` em `mock.test.ts`**

Adicionar estes 2 `it` blocks dentro do `describe('mockLiveApi', ...)` já existente (depois dos 2 testes atuais):

```ts
  it('TEMP-EXP-01 mantem comportamento existente: nunca cruza a faixa (sempre ok/warn)', () => {
    vi.useFakeTimers()
    const states = new Set<string>()
    const unsub = mockLiveApi.subscribe('TEMP-EXP-01', (p) => states.add(p.alarm_state))
    vi.advanceTimersByTime(20000)
    unsub()
    expect(states.has('crit')).toBe(false)
  })

  it('TEMP-PRE-01 (Preparo) cruza a faixa periodicamente: produz crit', () => {
    vi.useFakeTimers()
    const states = new Set<string>()
    const unsub = mockLiveApi.subscribe('TEMP-PRE-01', (p) => states.add(p.alarm_state))
    vi.advanceTimersByTime(20000)
    unsub()
    expect(states.has('crit')).toBe(true)
  })

  it('TEMP-ARS-01 (sem threshold) sempre reporta ok, independente do valor', () => {
    vi.useFakeTimers()
    const states = new Set<string>()
    const unsub = mockLiveApi.subscribe('TEMP-ARS-01', (p) => states.add(p.alarm_state))
    vi.advanceTimersByTime(20000)
    unsub()
    expect([...states]).toEqual(['ok'])
  })
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/lib/api/mock/mock.test.ts`
Expected: FAIL — `mockLiveApi` ainda usa a `THRESHOLD` única (Expurgo) pra qualquer código; `TEMP-PRE-01` nunca cruza a faixa com os parâmetros atuais.

- [ ] **Step 3: Reescrever `liveApi.ts`**

Substituir `frontend/src/lib/api/mock/liveApi.ts`:

```ts
import type { LiveApi } from '../contracts'
import type { LivePoint } from '../../types'
import { THRESHOLDS } from './fixtures'
import { computeStatus } from '../../status'

const TICK_MS = 1000

// Amplitude como fracao da faixa do threshold. Expurgo mantem o comportamento
// existente (fica confortavelmente dentro da faixa, sem alteracao observavel).
// Preparo usa amplitude maior, propositalmente: cruza a faixa periodicamente e
// produz 'crit' de vez em quando — a Overview usa isto pra ter uma area com
// alarme ativo pra mostrar (nao seria possivel demonstrar a badge de contagem
// se todo sensor mockado ficasse sempre dentro da faixa).
const AMP_FRACTION: Record<string, number> = {
  'TEMP-EXP-01': 1 / 2.2,
  'TEMP-PRE-01': 1 / 1.4,
}
const DEFAULT_AMP_FRACTION = 1 / 2.2

// Sensor sem threshold (Arsenal): nao ha faixa da qual derivar ponto medio ou
// amplitude — usa uma leitura ambiente plausivel, fixa.
const NO_THRESHOLD_MID = 24
const NO_THRESHOLD_AMP = 3

export const mockLiveApi: LiveApi = {
  subscribe(sensor_code, cb) {
    const threshold = THRESHOLDS[sensor_code] ?? null
    const mid = threshold ? (threshold.limite_min + threshold.limite_max) / 2 : NO_THRESHOLD_MID
    const amp = threshold
      ? (threshold.limite_max - threshold.limite_min) * (AMP_FRACTION[sensor_code] ?? DEFAULT_AMP_FRACTION)
      : NO_THRESHOLD_AMP
    let i = 0
    let ts = 1_700_000_000_000
    const id = setInterval(() => {
      ts += TICK_MS
      const value = +(mid + amp * Math.sin(i / 6)).toFixed(2)
      i++
      const state = computeStatus(value, threshold).state
      const alarm_state = state === 'unknown' ? 'ok' : state
      const point: LivePoint = { sensor_code, ts, value, alarm_state }
      cb(point)
    }, TICK_MS)
    return () => clearInterval(id)
  },
}
```

- [ ] **Step 4: Rodar testes (devem passar)**

Run: `cd frontend && npx vitest run src/lib/api/mock/mock.test.ts`
Expected: PASS — todos, incluindo os 4 testes de `mockLiveApi` (2 existentes + 2 novos) e os 3 recém-adicionados neste Step 1.

Run: `cd frontend && npm test`
Expected: PASS — suite completa (`useLiveTail.test.tsx` usa código `'x'`, que agora cai no ramo sem-threshold; não afeta suas asserções de contagem/monotonicidade/unsubscribe).

- [ ] **Step 5: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add frontend/src/lib/api/mock/liveApi.ts frontend/src/lib/api/mock/mock.test.ts
git commit -m "feat(frontend): liveApi parametrizado por sensor (Preparo cruza a faixa, Arsenal sem threshold)"
```

---

### Task 3: `lib/aggregateStatus.ts` — agregação pura (status por sensor, pior estado, agrupamento por área)

**Files:**
- Create: `frontend/src/lib/aggregateStatus.ts`
- Create: `frontend/src/lib/aggregateStatus.test.ts`

**Interfaces:**
- Consumes: `StatusResult['state']` (`lib/status.ts`), `Threshold`, `LivePoint`, `SensorMeta` (`lib/types.ts`).
- Produces:
  - `sensorDisplayState(threshold: Threshold | null, live: LivePoint | undefined): StatusResult['state']`
  - `worstAlarmState(states: StatusResult['state'][]): StatusResult['state']`
  - `type AreaGroup = { area: SensorMeta['area']; sensors: SensorMeta[] }`
  - `groupSensorsByArea(sensors: SensorMeta[]): AreaGroup[]`

- [ ] **Step 1: Escrever testes (falha)**

`frontend/src/lib/aggregateStatus.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { sensorDisplayState, worstAlarmState, groupSensorsByArea } from './aggregateStatus'
import type { LivePoint, SensorMeta, Threshold } from './types'

const t: Threshold = { sensor_id: 'S', limite_min: 18, limite_max: 22, is_valor_padrao_regulatorio: true }
const okPoint: LivePoint = { sensor_code: 'S', ts: 1, value: 20, alarm_state: 'ok' }
const critPoint: LivePoint = { sensor_code: 'S', ts: 1, value: 30, alarm_state: 'crit' }

describe('sensorDisplayState', () => {
  it('sem threshold e sempre unknown, mesmo com feed reportando ok', () => {
    expect(sensorDisplayState(null, okPoint)).toBe('unknown')
  })
  it('sem dado ao vivo ainda e unknown', () => {
    expect(sensorDisplayState(t, undefined)).toBe('unknown')
  })
  it('com threshold e dado, usa o alarm_state do feed', () => {
    expect(sensorDisplayState(t, okPoint)).toBe('ok')
    expect(sensorDisplayState(t, critPoint)).toBe('crit')
  })
})

describe('worstAlarmState', () => {
  it('vazio e unknown', () => {
    expect(worstAlarmState([])).toBe('unknown')
  })
  it('todos ok e ok', () => {
    expect(worstAlarmState(['ok', 'ok'])).toBe('ok')
  })
  it('um crit entre varios ok e crit', () => {
    expect(worstAlarmState(['ok', 'crit', 'ok'])).toBe('crit')
  })
  it('um warn entre ok (sem crit) e warn', () => {
    expect(worstAlarmState(['ok', 'warn'])).toBe('warn')
  })
  it('crit tem prioridade sobre warn', () => {
    expect(worstAlarmState(['warn', 'crit'])).toBe('crit')
  })
  it('todos unknown e unknown', () => {
    expect(worstAlarmState(['unknown', 'unknown'])).toBe('unknown')
  })
})

describe('groupSensorsByArea', () => {
  const sExp: SensorMeta = {
    sensor_code: 'A', name: 'a', unidade: 'C', protocolo_origem: 'rs485',
    measurement_type: { code: 'temperatura', name: 'Temperatura' },
    area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' },
  }
  const sPre: SensorMeta = {
    ...sExp, sensor_code: 'B',
    area: { area_code: 'PREPARO_ESTER', name: 'Preparo/Esterilização', category: 'Preparo/Esterilização' },
  }
  const sExp2: SensorMeta = { ...sExp, sensor_code: 'C' }

  it('agrupa sensores pela area_code, preservando ordem de primeira ocorrencia', () => {
    const groups = groupSensorsByArea([sExp, sPre, sExp2])
    expect(groups).toHaveLength(2)
    expect(groups[0].area.area_code).toBe('EXPURGO')
    expect(groups[0].sensors.map((s) => s.sensor_code)).toEqual(['A', 'C'])
    expect(groups[1].area.area_code).toBe('PREPARO_ESTER')
    expect(groups[1].sensors.map((s) => s.sensor_code)).toEqual(['B'])
  })
  it('lista vazia devolve grupos vazios', () => {
    expect(groupSensorsByArea([])).toEqual([])
  })
})
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/lib/aggregateStatus.test.ts`
Expected: FAIL — `./aggregateStatus` não existe.

- [ ] **Step 3: Implementar**

`frontend/src/lib/aggregateStatus.ts`:

```ts
import type { StatusResult } from './status'
import type { LivePoint, SensorMeta, Threshold } from './types'

// Estado a exibir para 1 sensor. Sem threshold configurado (ou sem dado ao
// vivo ainda) -> 'unknown' ("Sem limite"), MESMO que o feed reporte
// alarm_state 'ok' internamente — a convencao do liveApi mapeia
// 'unknown'->'ok' na emissao (porque LivePoint.alarm_state nao tem variante
// 'unknown'); aqui reconstruimos a distincao a partir do threshold, que e a
// fonte de verdade sobre "esta configurado" e a UI PRECISA mostrar
// corretamente (ver Global Constraints do plano).
export function sensorDisplayState(
  threshold: Threshold | null,
  live: LivePoint | undefined,
): StatusResult['state'] {
  if (!threshold || !live) return 'unknown'
  return live.alarm_state
}

const SEVERITY: Record<StatusResult['state'], number> = { unknown: 0, ok: 1, warn: 2, crit: 3 }

// Pior estado entre varios sensores (crit > warn > ok > unknown). Array vazio
// -> 'unknown' (nada para agregar).
export function worstAlarmState(states: StatusResult['state'][]): StatusResult['state'] {
  if (states.length === 0) return 'unknown'
  return states.reduce((worst, s) => (SEVERITY[s] > SEVERITY[worst] ? s : worst), states[0])
}

export type AreaGroup = { area: SensorMeta['area']; sensors: SensorMeta[] }

// Agrupa sensores por area_code, preservando a ordem de primeira ocorrencia
// (nao ordena alfabeticamente — a ordem de listSensors() e a ordem de
// exibicao).
export function groupSensorsByArea(sensors: SensorMeta[]): AreaGroup[] {
  const map = new Map<string, AreaGroup>()
  for (const s of sensors) {
    const key = s.area.area_code
    const existing = map.get(key)
    if (existing) existing.sensors.push(s)
    else map.set(key, { area: s.area, sensors: [s] })
  }
  return [...map.values()]
}
```

- [ ] **Step 4: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/lib/aggregateStatus.test.ts`
Expected: PASS — todos.

- [ ] **Step 5: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add frontend/src/lib/aggregateStatus.ts frontend/src/lib/aggregateStatus.test.ts
git commit -m "feat(frontend): lib/aggregateStatus — sensorDisplayState, worstAlarmState, groupSensorsByArea"
```

---

### Task 4: `useLiveStatuses` — hook multi-sensor (último valor por código, sem buffer)

**Files:**
- Create: `frontend/src/lib/useLiveStatuses.ts`
- Create: `frontend/src/lib/useLiveStatuses.test.tsx`

**Interfaces:**
- Consumes: `liveApi` (`lib/api`), `LivePoint` (`lib/types`).
- Produces: `useLiveStatuses(codes: string[]): Record<string, LivePoint>`.

- [ ] **Step 1: Escrever testes (falha)**

`frontend/src/lib/useLiveStatuses.test.tsx`:

```tsx
import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useLiveStatuses } from './useLiveStatuses'
import { liveApi } from './api'

afterEach(() => vi.useRealTimers())

describe('useLiveStatuses', () => {
  it('acumula o ultimo ponto por sensor_code', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useLiveStatuses(['TEMP-EXP-01', 'TEMP-PRE-01']))
    act(() => { vi.advanceTimersByTime(2500) })
    expect(result.current['TEMP-EXP-01']).toBeDefined()
    expect(result.current['TEMP-PRE-01']).toBeDefined()
    expect(result.current['TEMP-EXP-01'].sensor_code).toBe('TEMP-EXP-01')
  })

  it('chama unsubscribe de TODOS os codigos no unmount (nao vaza timer)', () => {
    const unsubs = [vi.fn(), vi.fn()]
    let call = 0
    const spy = vi.spyOn(liveApi, 'subscribe').mockImplementation(() => unsubs[call++])
    const { unmount } = renderHook(() => useLiveStatuses(['TEMP-EXP-01', 'TEMP-PRE-01']))
    expect(unsubs[0]).not.toHaveBeenCalled()
    expect(unsubs[1]).not.toHaveBeenCalled()
    unmount()
    expect(unsubs[0]).toHaveBeenCalledTimes(1)
    expect(unsubs[1]).toHaveBeenCalledTimes(1)
    spy.mockRestore()
  })

  it('nao re-assina quando `codes` muda de referencia mas mantem o mesmo conteudo', () => {
    const spy = vi.spyOn(liveApi, 'subscribe')
    const { rerender } = renderHook(({ codes }) => useLiveStatuses(codes), {
      initialProps: { codes: ['TEMP-EXP-01', 'TEMP-PRE-01'] },
    })
    const callsAfterFirst = spy.mock.calls.length
    rerender({ codes: ['TEMP-EXP-01', 'TEMP-PRE-01'] }) // novo array, mesmo conteudo
    expect(spy.mock.calls.length).toBe(callsAfterFirst) // nao re-assinou
    spy.mockRestore()
  })

  it('re-assina quando o CONTEUDO de `codes` muda', () => {
    const spy = vi.spyOn(liveApi, 'subscribe')
    const { rerender } = renderHook(({ codes }) => useLiveStatuses(codes), {
      initialProps: { codes: ['TEMP-EXP-01'] },
    })
    const callsAfterFirst = spy.mock.calls.length
    rerender({ codes: ['TEMP-EXP-01', 'TEMP-ARS-01'] })
    expect(spy.mock.calls.length).toBeGreaterThan(callsAfterFirst)
    spy.mockRestore()
  })
})
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/lib/useLiveStatuses.test.tsx`
Expected: FAIL — `./useLiveStatuses` não existe.

- [ ] **Step 3: Implementar**

`frontend/src/lib/useLiveStatuses.ts`:

```ts
import { useEffect, useState } from 'react'
import { liveApi } from './api'
import type { LivePoint } from './types'

// Analogo a useLiveTail, mas sem buffer: guarda so o ULTIMO LivePoint por
// sensor_code (Overview so precisa do estado atual de cada sensor, nao do
// historico da cauda).
//
// `codes.join(',')` como chave do efeito (nao `codes` direto): o array chega
// recriado a cada render do chamador (ex.: `sensors.map(s => s.sensor_code)`),
// e usar a referencia direta re-assinaria (e zeraria o estado) a cada render.
// Seguro para o formato de sensor_code deste projeto (sem virgula).
export function useLiveStatuses(codes: string[]): Record<string, LivePoint> {
  const [byCode, setByCode] = useState<Record<string, LivePoint>>({})
  const codesKey = codes.join(',')

  useEffect(() => {
    setByCode({})
    const unsubs = codes.map((code) =>
      liveApi.subscribe(code, (p) => {
        setByCode((prev) => ({ ...prev, [code]: p }))
      }),
    )
    return () => unsubs.forEach((unsub) => unsub())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codesKey])

  return byCode
}
```

- [ ] **Step 4: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/lib/useLiveStatuses.test.tsx`
Expected: PASS — todos os 4.

- [ ] **Step 5: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add frontend/src/lib/useLiveStatuses.ts frontend/src/lib/useLiveStatuses.test.tsx
git commit -m "feat(frontend): useLiveStatuses — ultimo valor ao vivo por sensor, multi-codigo"
```

---

### Task 5: Extrair `statusVisuals.tsx` (ícone + cor de status) e refatorar `LiveReadout`

**Files:**
- Create: `frontend/src/components/statusVisuals.tsx`
- Modify: `frontend/src/components/LiveReadout.tsx`

**Interfaces:**
- Produces: `StatusIcon({state}): JSX.Element`, `statusTextColor(state: StatusResult['state']): string`.
- Consumes (por `AreaCard`, Task 7, e por `LiveReadout` já existente): os dois exports acima.

Este é um refactor puro — **nenhuma mudança de comportamento**. A verificação é rodar a suite completa antes e depois (não há novo teste de comportamento; `LiveReadout.test.tsx` já cobre o resultado visual e deve continuar 100% verde, byte-idêntico em resultado).

- [ ] **Step 1: Rodar a suite completa (baseline, deve estar verde antes de tocar nada)**

Run: `cd frontend && npm test`
Expected: PASS — todos (baseline antes do refactor).

- [ ] **Step 2: Criar `statusVisuals.tsx` com o código extraído de `LiveReadout.tsx`**

`frontend/src/components/statusVisuals.tsx`:

```tsx
import type { StatusResult } from '../lib/status'

type State = StatusResult['state']

// Cor de texto/icone derivada do token de estado, misturada com --color-ink
// para garantir >=4.5:1 de contraste em ambos os temas (o token puro de
// warn/good sozinho nao passa em WCAG AA sobre a superficie clara).
// Proporcao 60/40 verificada por script (conversao OKLCH->sRGB completa,
// incluindo interpolacao de matiz) contra --color-surface nos dois temas;
// pior caso e warn no tema claro, com contraste ~5.7:1 (margem sobre 4.5:1).
const TEXT_COLOR: Record<State, string> = {
  ok: 'color-mix(in oklch, var(--color-good) 60%, var(--color-ink) 40%)',
  warn: 'color-mix(in oklch, var(--color-warn) 60%, var(--color-ink) 40%)',
  crit: 'color-mix(in oklch, var(--color-crit) 60%, var(--color-ink) 40%)',
  unknown: 'var(--color-muted)',
}

export function statusTextColor(state: State): string {
  return TEXT_COLOR[state]
}

export function StatusIcon({ state }: { state: State }) {
  const common = { width: 14, height: 14, viewBox: '0 0 16 16', fill: 'currentColor' }
  switch (state) {
    case 'ok':
      return (
        <svg {...common} aria-hidden="true">
          <circle cx="8" cy="8" r="6" />
        </svg>
      )
    case 'warn':
      return (
        <svg {...common} aria-hidden="true">
          <path d="M8 1.6 15 14.4H1L8 1.6Z" />
        </svg>
      )
    case 'crit':
      return (
        <svg {...common} aria-hidden="true">
          <rect x="2.2" y="2.2" width="11.6" height="11.6" rx="2" />
        </svg>
      )
    case 'unknown':
      return (
        <svg {...common} fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
          <circle cx="8" cy="8" r="5.6" strokeDasharray="2.4 2.4" />
        </svg>
      )
  }
}
```

- [ ] **Step 3: Refatorar `LiveReadout.tsx` para importar de `statusVisuals`**

Editar `frontend/src/components/LiveReadout.tsx`:

1. Trocar o import do topo:

```tsx
import { computeStatus, LABELS, type StatusResult } from '../lib/status'
import type { Threshold, AlarmState } from '../lib/types'
import { ToleranceRail } from './ToleranceRail'
```

por:

```tsx
import { computeStatus, LABELS, type StatusResult } from '../lib/status'
import type { Threshold, AlarmState } from '../lib/types'
import { ToleranceRail } from './ToleranceRail'
import { StatusIcon, statusTextColor } from './statusVisuals'
```

2. **Remover** do arquivo o bloco `const TEXT_COLOR: Record<State, string> = {...}` inteiro e a função `function StatusIcon({ state }: { state: State }) {...}` inteira (agora vivem em `statusVisuals.tsx`). Manter o `type State = StatusResult['state']` (ainda usado localmente).

3. No JSX, trocar `style={{ color: TEXT_COLOR[st] }}` por `style={{ color: statusTextColor(st) }}`. O resto do componente (estrutura, `ToleranceRail`, valores, classes) **não muda**.

- [ ] **Step 4: Rodar a suite completa (deve continuar 100% verde, sem nenhuma mudança de resultado)**

Run: `cd frontend && npm test`
Expected: PASS — mesma contagem de testes do baseline (Step 1), todos verdes. Nenhum teste de `LiveReadout.test.tsx` deve ter mudado de comportamento.

Run: `cd frontend && npm run build`
Expected: build limpo (confirma que não sobrou import morto/quebrado).

- [ ] **Step 5: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add frontend/src/components/statusVisuals.tsx frontend/src/components/LiveReadout.tsx
git commit -m "refactor(frontend): extrai StatusIcon/statusTextColor p/ statusVisuals.tsx (reuso no AreaCard)"
```

---

### Task 6: `useSensors` + `useThresholds` em `queries.ts`

**Files:**
- Modify: `frontend/src/lib/queries.ts`
- Modify: `frontend/src/lib/queries.test.tsx`

**Interfaces:**
- Consumes: `metaApi` (`lib/api`).
- Produces: `useSensors(): UseQueryResult<SensorMeta[]>`, `useThresholds(codes: string[]): UseQueryResult<Threshold | null>[]` (mesma ordem de `codes`; usa `useQueries` do TanStack, reaproveitando a `queryKey` `['threshold', code]` já usada por `useThreshold` — cache compartilhado).

- [ ] **Step 1: Escrever testes (falha) — adicionar ao final de `queries.test.tsx`**

Adicionar ao final do `describe('queries', ...)` existente em `frontend/src/lib/queries.test.tsx`:

```tsx
  it('useSensors lista os 3 sensores', async () => {
    const { result } = renderHook(() => useSensors(), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.map((s) => s.sensor_code).sort()).toEqual([
      'TEMP-ARS-01', 'TEMP-EXP-01', 'TEMP-PRE-01',
    ])
  })

  it('useThresholds devolve um resultado por codigo, na mesma ordem', async () => {
    const { result } = renderHook(
      () => useThresholds(['TEMP-EXP-01', 'TEMP-ARS-01']),
      { wrapper: wrapper() },
    )
    await waitFor(() => expect(result.current.every((r) => r.isSuccess)).toBe(true))
    expect(result.current[0].data?.limite_max).toBe(22)
    expect(result.current[1].data).toBeNull() // Arsenal, sem threshold
  })
```

E ajustar o import do topo do arquivo:

```tsx
import { useSensorMeta, useThreshold, useHistory, useSensors, useThresholds } from './queries'
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/lib/queries.test.tsx`
Expected: FAIL — `useSensors`/`useThresholds` não existem em `queries.ts`.

- [ ] **Step 3: Implementar**

Em `frontend/src/lib/queries.ts`, trocar o import do topo:

```ts
import { useQuery } from '@tanstack/react-query'
import { metaApi, historyApi } from './api'
import type { Window } from './types'
```

por:

```ts
import { useQuery, useQueries } from '@tanstack/react-query'
import { metaApi, historyApi } from './api'
import type { Window } from './types'
```

E adicionar ao final do arquivo:

```ts
export function useSensors() {
  return useQuery({ queryKey: ['sensors'], queryFn: () => metaApi.listSensors() })
}

// Mesma queryKey de useThreshold (['threshold', code]) — cache compartilhado:
// se um sensor ja foi visto no Detalhe do Sensor, a Overview reusa o cache.
export function useThresholds(codes: string[]) {
  return useQueries({
    queries: codes.map((code) => ({
      queryKey: ['threshold', code],
      queryFn: () => metaApi.getThreshold(code),
    })),
  })
}
```

- [ ] **Step 4: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/lib/queries.test.tsx`
Expected: PASS — todos.

Run: `cd frontend && npm test`
Expected: PASS — suite completa.

- [ ] **Step 5: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add frontend/src/lib/queries.ts frontend/src/lib/queries.test.tsx
git commit -m "feat(frontend): useSensors + useThresholds (useQueries) em queries.ts"
```

---

### Task 7: `AreaCard`

**Files:**
- Create: `frontend/src/components/AreaCard.tsx`
- Create: `frontend/src/components/AreaCard.test.tsx`

**Interfaces:**
- Consumes: `AreaGroup`, `sensorDisplayState`, `worstAlarmState` (`lib/aggregateStatus.ts`), `LABELS` (`lib/status.ts`), `StatusIcon`, `statusTextColor` (`components/statusVisuals.tsx`), `Threshold`, `LivePoint` (`lib/types`).
- Produces: `<AreaCard group={AreaGroup} thresholdsByCode={Record<string, Threshold|null|undefined>} liveByCode={Record<string, LivePoint|undefined>} />`.

- [ ] **Step 1: Escrever testes (falha)**

`frontend/src/components/AreaCard.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AreaCard } from './AreaCard'
import type { AreaGroup } from '../lib/aggregateStatus'
import type { LivePoint, Threshold } from '../lib/types'

const expurgo: AreaGroup = {
  area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' },
  sensors: [{
    sensor_code: 'TEMP-EXP-01', name: 'Temperatura', unidade: 'C', protocolo_origem: 'rs485',
    measurement_type: { code: 'temperatura', name: 'Temperatura' },
    area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' },
  }],
}
const t: Threshold = { sensor_id: 'TEMP-EXP-01', limite_min: 18, limite_max: 22, is_valor_padrao_regulatorio: true }

describe('AreaCard', () => {
  it('mostra nome e categoria da area', () => {
    render(<AreaCard group={expurgo} thresholdsByCode={{ 'TEMP-EXP-01': t }} liveByCode={{}} />)
    expect(screen.getByText('Expurgo')).toBeInTheDocument()
  })

  it('sensor ok: mostra "Dentro da faixa", sem badge de alarme', () => {
    const live: LivePoint = { sensor_code: 'TEMP-EXP-01', ts: 1, value: 20, alarm_state: 'ok' }
    render(<AreaCard group={expurgo} thresholdsByCode={{ 'TEMP-EXP-01': t }} liveByCode={{ 'TEMP-EXP-01': live }} />)
    expect(screen.getByText('Dentro da faixa')).toBeInTheDocument()
    expect(screen.queryByText(/alarme/i)).not.toBeInTheDocument()
  })

  it('sensor crit: mostra "Fora da faixa" E badge "1 alarme"', () => {
    const live: LivePoint = { sensor_code: 'TEMP-EXP-01', ts: 1, value: 30, alarm_state: 'crit' }
    render(<AreaCard group={expurgo} thresholdsByCode={{ 'TEMP-EXP-01': t }} liveByCode={{ 'TEMP-EXP-01': live }} />)
    expect(screen.getByText('Fora da faixa')).toBeInTheDocument()
    expect(screen.getByText('1 alarme')).toBeInTheDocument()
  })

  it('sensor sem threshold (Arsenal): mostra "Sem limite", mesmo com feed ok', () => {
    const arsenal: AreaGroup = {
      area: { area_code: 'ARSENAL', name: 'Arsenal', category: 'Arsenal' },
      sensors: [{
        sensor_code: 'TEMP-ARS-01', name: 'Temperatura', unidade: 'C', protocolo_origem: 'rs485',
        measurement_type: { code: 'temperatura', name: 'Temperatura' },
        area: { area_code: 'ARSENAL', name: 'Arsenal', category: 'Arsenal' },
      }],
    }
    const live: LivePoint = { sensor_code: 'TEMP-ARS-01', ts: 1, value: 24, alarm_state: 'ok' }
    render(<AreaCard group={arsenal} thresholdsByCode={{ 'TEMP-ARS-01': null }} liveByCode={{ 'TEMP-ARS-01': live }} />)
    expect(screen.getByText('Sem limite')).toBeInTheDocument()
  })

  it('status sempre vem com icone (nao so cor) — svg presente junto ao texto', () => {
    const live: LivePoint = { sensor_code: 'TEMP-EXP-01', ts: 1, value: 30, alarm_state: 'crit' }
    const { container } = render(
      <AreaCard group={expurgo} thresholdsByCode={{ 'TEMP-EXP-01': t }} liveByCode={{ 'TEMP-EXP-01': live }} />,
    )
    expect(container.querySelector('svg')).not.toBeNull()
  })
})
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/components/AreaCard.test.tsx`
Expected: FAIL — `./AreaCard` não existe.

- [ ] **Step 3: Implementar**

`frontend/src/components/AreaCard.tsx`:

```tsx
import { LABELS } from '../lib/status'
import { sensorDisplayState, worstAlarmState, type AreaGroup } from '../lib/aggregateStatus'
import { StatusIcon, statusTextColor } from './statusVisuals'
import type { LivePoint, Threshold } from '../lib/types'

export function AreaCard({
  group,
  thresholdsByCode,
  liveByCode,
}: {
  group: AreaGroup
  thresholdsByCode: Record<string, Threshold | null | undefined>
  liveByCode: Record<string, LivePoint | undefined>
}) {
  const states = group.sensors.map((s) =>
    sensorDisplayState(thresholdsByCode[s.sensor_code] ?? null, liveByCode[s.sensor_code]),
  )
  const aggregate = worstAlarmState(states)
  const critCount = states.filter((s) => s === 'crit').length

  return (
    <div
      className="rounded-2xl p-5"
      style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold" style={{ color: 'var(--color-ink)' }}>
            {group.area.name}
          </h2>
          <p className="mt-0.5 text-xs" style={{ color: 'var(--color-muted)' }}>
            {group.area.category}
          </p>
        </div>
        {critCount > 0 && (
          <span
            className="rounded-full px-2 py-0.5 text-xs font-semibold"
            style={{ background: 'var(--color-panel)', color: 'var(--color-crit)' }}
          >
            {critCount} {critCount === 1 ? 'alarme' : 'alarmes'}
          </span>
        )}
      </div>

      <div
        className="mt-4 flex items-center gap-2 text-sm font-semibold"
        style={{ color: statusTextColor(aggregate) }}
      >
        <StatusIcon state={aggregate} />
        <span>{LABELS[aggregate]}</span>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/components/AreaCard.test.tsx`
Expected: PASS — todos os 5.

- [ ] **Step 5: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add frontend/src/components/AreaCard.tsx frontend/src/components/AreaCard.test.tsx
git commit -m "feat(frontend): AreaCard — status agregado + badge de alarmes ativos"
```

---

### Task 8: `OverviewPage` + wiring do `App.tsx`

**Files:**
- Create: `frontend/src/pages/OverviewPage.tsx`
- Create: `frontend/src/pages/OverviewPage.test.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `useSensors`, `useThresholds` (`lib/queries.ts`), `useLiveStatuses` (`lib/useLiveStatuses.ts`), `groupSensorsByArea` (`lib/aggregateStatus.ts`), `AreaCard` (`components/AreaCard.tsx`), `ThemeToggle` (`components/ThemeToggle.tsx`, já existe).
- Produces: `<OverviewPage />`. `App.tsx` renderiza `<OverviewPage />` no lugar de `<SensorDetailPage code="TEMP-EXP-01" />`.

- [ ] **Step 1: Escrever testes (falha)**

`frontend/src/pages/OverviewPage.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { OverviewPage } from './OverviewPage'
import * as api from '../lib/api'

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{node}</QueryClientProvider>
}

describe('OverviewPage', () => {
  it('renderiza as 3 areas apos carregar', async () => {
    render(wrap(<OverviewPage />))
    await waitFor(() => expect(screen.getByText('Expurgo')).toBeInTheDocument())
    expect(screen.getByText('Preparo/Esterilização')).toBeInTheDocument()
    expect(screen.getByText('Arsenal')).toBeInTheDocument()
  })

  it('Arsenal mostra "Sem limite" (sem threshold configurado)', async () => {
    render(wrap(<OverviewPage />))
    await waitFor(() => expect(screen.getByText('Arsenal')).toBeInTheDocument())
    // Ha 1 card por area; o texto "Sem limite" so deve aparecer pro Arsenal.
    await waitFor(() => expect(screen.getByText('Sem limite')).toBeInTheDocument())
  })

  it('erro ao listar sensores mostra retry, que refaz a chamada', async () => {
    const spy = vi.spyOn(api.metaApi, 'listSensors').mockRejectedValueOnce(new Error('falhou'))
    render(wrap(<OverviewPage />))
    await waitFor(() => expect(screen.getByText(/falha/i)).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: /tentar de novo/i }))
    await waitFor(() => expect(screen.getByText('Expurgo')).toBeInTheDocument())
    spy.mockRestore()
  })
})
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/pages/OverviewPage.test.tsx`
Expected: FAIL — `./OverviewPage` não existe.

- [ ] **Step 3: Implementar `OverviewPage.tsx`**

`frontend/src/pages/OverviewPage.tsx`:

```tsx
import { useSensors, useThresholds } from '../lib/queries'
import { useLiveStatuses } from '../lib/useLiveStatuses'
import { groupSensorsByArea } from '../lib/aggregateStatus'
import { AreaCard } from '../components/AreaCard'
import { ThemeToggle } from '../components/ThemeToggle'

function SkeletonCard() {
  return (
    <div
      className="h-28 animate-pulse rounded-2xl motion-reduce:animate-none"
      style={{ background: 'var(--color-line)' }}
      aria-hidden="true"
    />
  )
}

export function OverviewPage() {
  const sensorsQuery = useSensors()
  const sensors = sensorsQuery.data ?? []
  const codes = sensors.map((s) => s.sensor_code)
  const thresholdResults = useThresholds(codes)
  const thresholdsByCode = Object.fromEntries(codes.map((c, i) => [c, thresholdResults[i]?.data]))
  const liveByCode = useLiveStatuses(codes)
  const groups = groupSensorsByArea(sensors)
  const ready = sensorsQuery.isSuccess && thresholdResults.every((r) => r.isSuccess)

  return (
    <div className="mx-auto max-w-5xl p-4 sm:p-6">
      <header className="mb-6 flex items-center justify-between gap-4">
        <h1 className="text-xl font-bold" style={{ color: 'var(--color-ink)' }}>
          Visão geral
        </h1>
        <ThemeToggle />
      </header>

      {sensorsQuery.isError ? (
        <div
          className="flex h-40 flex-col items-center justify-center gap-2 text-center text-sm"
          style={{ color: 'var(--color-crit)' }}
        >
          <span>Falha ao carregar as áreas.</span>
          <button
            type="button"
            className="min-h-11 rounded-md px-3 font-semibold underline outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
            onClick={() => sensorsQuery.refetch()}
          >
            Tentar de novo
          </button>
        </div>
      ) : (
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
          {!ready
            ? Array.from({ length: 3 }, (_, i) => <SkeletonCard key={i} />)
            : groups.map((g) => (
                <AreaCard key={g.area.area_code} group={g} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode} />
              ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Wiring do `App.tsx`**

Substituir `frontend/src/App.tsx`:

```tsx
import { OverviewPage } from './pages/OverviewPage'

export default function App() {
  return <OverviewPage />
}
```

- [ ] **Step 5: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/pages/OverviewPage.test.tsx`
Expected: PASS — todos os 3.

- [ ] **Step 6: Suite completa + build**

Run: `cd frontend && npm test`
Expected: PASS — suite completa (nenhuma regressão em `SensorDetailPage.test.tsx`, que continua testável isoladamente mesmo sem estar montada em `App.tsx`).

Run: `cd frontend && npm run build`
Expected: build limpo.

- [ ] **Step 7: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add frontend/src/pages/OverviewPage.tsx frontend/src/pages/OverviewPage.test.tsx frontend/src/App.tsx
git commit -m "feat(frontend): OverviewPage integrada, vira a tela raiz (App.tsx)"
```

---

## Self-Review

**Spec coverage:** §1 escopo (só cliente, sem nav, Overview na raiz) → Task 8. §2 dados mock 3 sensores + `listSensors` → Task 1. §2.2 liveApi por sensor → Task 2. §3 agregação (`worstAlarmState`, contagem só crit) → Task 3, Task 7. §4 `useLiveStatuses` → Task 4. §5 componentes (`AreaCard`/`OverviewPage`) → Task 7, Task 8. §6 fluxo de dados → Task 8. §7 erro/loading → Task 8. §8 testes 1–5 → Task 3 (1), Task 1/2 (2), Task 4 (3), Task 7 (4), Task 8 (5). §9 entregáveis → todas as tasks + verificação visual (feita pelo controller após a Task 8, fora do escopo de subagent — ver nota abaixo).

**Nota sobre verificação visual:** o slice anterior (Detalhe do Sensor) provou que testes com dependências mockadas (lá, ECharts) escondem bugs reais de render. A Overview não usa ECharts, mas o mesmo risco genérico existe (grid CSS, contraste, visibilidade condicional da badge). Após a Task 8 e a review final de branch, rodar a mesma verificação visual real (playwright+chromium, light+dark) feita no slice anterior, antes de considerar a fatia pronta.

**Placeholder scan:** sem TBD/TODO; todo passo tem código completo.

**Type consistency:** `AreaGroup` definido uma vez em `aggregateStatus.ts` (Task 3), consumido idêntico por `AreaCard` (Task 7) e `OverviewPage` (Task 8). `sensorDisplayState`/`worstAlarmState` mesma assinatura em todos os usos. `MetaApi.listSensors()` consistente entre `contracts.ts`, `metaApi.ts` e `queries.ts`. `useThresholds(codes)` devolve array na mesma ordem de `codes` — documentado e usado corretamente em `OverviewPage` (`thresholdResults[i]`).

**Risco assumido e mitigado:** a mudança de comportamento de `getSensor`/`getThreshold` (passam a rejeitar código desconhecido) quebra os 4 testes pré-existentes que usavam o código genérico `'x'` — todos os 4 são identificados e corrigidos explicitamente nas Tasks 1 e 6 (2 em `mock.test.ts`, 2 em `queries.test.tsx`). `useLiveTail.test.tsx` também usa `'x'` mas não quebra (só passa por `liveApi`, que nunca lança erro para código desconhecido — cai no ramo sem-threshold).
