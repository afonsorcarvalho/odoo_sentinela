# Adapter real: liveApi (SSE) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trocar `mockLiveApi` por `realLiveApi`, consumindo o endpoint SSE real `GET /sensores/{code}/live?token=<jwt>` (já em `master`, ver `api/live.py`), plugado no mesmo switch `VITE_API_MODE` que já liga `authApi`/`metaApi`/`historyApi`.

**Architecture:** `frontend/src/lib/api/real/liveApi.ts` abre um `EventSource` autenticado via token na query string (browser não manda header customizado em `EventSource`), busca/cacheia o `Threshold` do sensor via `realMetaApi.getThreshold` já existente, e em cada evento roda `computeStatus` (já existente e testada) pra computar `alarm_state` no cliente — o wire do SSE não manda esse campo.

**Tech Stack:** Vite + React + TypeScript, Vitest (`environment: 'jsdom'` — sem `EventSource` nativo, precisa de um stub nos testes), mesmo padrão de `real/authApi.ts`/`real/metaApi.ts`/`real/historyApi.ts` já em `master`.

## Global Constraints

- URL do `EventSource`: `${BASE_URL}/sensores/${sensor_code}/live?token=${token}` — `BASE_URL` vem de `real/http.ts` (precisa ser exportado de lá, hoje é `const` privado do módulo).
- Payload de cada evento SSE (JSON dentro de `data:`): `{"sensor_id": string, "time": number, "valor": number}` — sem `alarm_state`.
- `LivePoint` emitido pro callback do `subscribe`: `{sensor_code, ts, value, alarm_state}` — `sensor_code` vem do parâmetro que o chamador passou pro `subscribe` (não do `sensor_id` do wire — são o mesmo sensor por construção, um `EventSource` por `subscribe`), `ts`/`value` vêm de `time`/`valor` do wire, `alarm_state` é computado localmente.
- `alarm_state`: `computeStatus(valor, threshold).state` — quando o estado for `'unknown'` (sensor sem threshold, ou threshold ainda não chegou), cair pra `'ok'` (mesma regra que `mock/liveApi.ts` já usa hoje).
- Se `realMetaApi.getThreshold` falhar (rejeitar), o `threshold` fica `null` (mesmo efeito de sensor sem threshold — fallback silencioso, sem lançar/travar o `subscribe`).
- `unsubscribe` (o retorno de `subscribe`) fecha o `EventSource` (`es.close()`) — sem lógica adicional de cleanup.
- `liveApi` entra no mesmo switch `VITE_API_MODE` de `frontend/src/lib/api/index.ts` que já liga `authApi`/`metaApi`/`historyApi`.
- Sem replay/backfill no reconnect — `EventSource` nativo já reconecta sozinho; isso é papel do `historyApi`, não deste adapter.

---

## Task 1: `realLiveApi` (EventSource + threshold + alarm_state)

**Files:**
- Modify: `frontend/src/lib/api/real/http.ts`
- Create: `frontend/src/lib/api/real/liveApi.ts`
- Test: `frontend/src/lib/api/real/liveApi.test.ts`

**Interfaces:**
- Consumes: `realMetaApi.getThreshold(code): Promise<Threshold | null>` (já existe, `frontend/src/lib/api/real/metaApi.ts`); `computeStatus(value, threshold): StatusResult` (já existe, `frontend/src/lib/status.ts`); `TOKEN_STORAGE_KEY` (já existe, `frontend/src/lib/useAuth.tsx`); tipo `LiveApi` de `frontend/src/lib/api/contracts.ts` (`subscribe(code, cb): () => void`).
- Produces: `BASE_URL` exportado de `real/http.ts` (usado por este adapter — os outros adapters reais usam `authFetchJson`, que já embute `BASE_URL` internamente, então não precisavam importá-lo); `realLiveApi: LiveApi` (usado pela Task 2).

- [ ] **Step 1: Exportar `BASE_URL` em `frontend/src/lib/api/real/http.ts`**

Arquivo atual:

```ts
import { TOKEN_STORAGE_KEY } from '../../useAuth'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001'

export async function authFetchJson<T>(path: string): Promise<T> {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) {
    throw new Error(`erro ${res.status} ao chamar ${path}`)
  }
  return res.json()
}
```

Trocar a linha `const BASE_URL = ...` por:

```ts
export const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001'
```

(resto do arquivo fica igual — só essa linha muda).

- [ ] **Step 2: Rodar os testes existentes de `http.ts` pra confirmar que o export não quebrou nada**

Run (a partir de `frontend/`): `npx vitest run src/lib/api/real/http.test.ts`
Expected: 3 passed (os mesmos de antes — exportar uma const não muda comportamento).

- [ ] **Step 3: Escrever o teste em `frontend/src/lib/api/real/liveApi.test.ts`**

```ts
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { realLiveApi } from './liveApi'
import { TOKEN_STORAGE_KEY } from '../../useAuth'
import * as metaApiModule from './metaApi'

class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  onmessage: ((ev: { data: string }) => void) | null = null
  closed = false
  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }
  close() {
    this.closed = true
  }
}

const THRESHOLD = { sensor_id: 'SNR-1', limite_min: 10, limite_max: 20, is_valor_padrao_regulatorio: false }

beforeEach(() => {
  MockEventSource.instances = []
  vi.stubGlobal('EventSource', MockEventSource)
})

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('realLiveApi', () => {
  it('subscribe abre EventSource com sensor_code e token na URL', () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'abc.def.ghi')
    vi.spyOn(metaApiModule.realMetaApi, 'getThreshold').mockResolvedValue(THRESHOLD)

    realLiveApi.subscribe('SNR-1', () => {})

    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0].url).toContain('/sensores/SNR-1/live')
    expect(MockEventSource.instances[0].url).toContain('token=abc.def.ghi')
  })

  it('onmessage computa alarm_state a partir do threshold cacheado e chama cb com LivePoint', async () => {
    vi.spyOn(metaApiModule.realMetaApi, 'getThreshold').mockResolvedValue(THRESHOLD)
    const cb = vi.fn()

    realLiveApi.subscribe('SNR-1', cb)
    await Promise.resolve()

    const es = MockEventSource.instances[0]
    es.onmessage?.({ data: JSON.stringify({ sensor_id: 'SNR-1', time: 1700000000000, valor: 15 }) })

    expect(cb).toHaveBeenCalledWith({
      sensor_code: 'SNR-1', ts: 1700000000000, value: 15, alarm_state: 'ok',
    })
  })

  it('valor fora da faixa do threshold gera alarm_state crit', async () => {
    vi.spyOn(metaApiModule.realMetaApi, 'getThreshold').mockResolvedValue(THRESHOLD)
    const cb = vi.fn()

    realLiveApi.subscribe('SNR-1', cb)
    await Promise.resolve()

    const es = MockEventSource.instances[0]
    es.onmessage?.({ data: JSON.stringify({ sensor_id: 'SNR-1', time: 1700000000000, valor: 99 }) })

    expect(cb).toHaveBeenCalledWith(expect.objectContaining({ alarm_state: 'crit' }))
  })

  it('threshold ainda nao chegou (mensagem antes do fetch resolver) cai em alarm_state ok', () => {
    // não mocka getThreshold — simula que a promise ainda não resolveu
    const cb = vi.fn()

    realLiveApi.subscribe('SNR-1', cb)
    // sem await — dispara a mensagem antes da promise de threshold resolver

    const es = MockEventSource.instances[0]
    es.onmessage?.({ data: JSON.stringify({ sensor_id: 'SNR-1', time: 1700000000000, valor: 999 }) })

    expect(cb).toHaveBeenCalledWith(expect.objectContaining({ alarm_state: 'ok' }))
  })

  it('unsubscribe fecha o EventSource', () => {
    vi.spyOn(metaApiModule.realMetaApi, 'getThreshold').mockResolvedValue(THRESHOLD)

    const unsubscribe = realLiveApi.subscribe('SNR-1', () => {})
    unsubscribe()

    expect(MockEventSource.instances[0].closed).toBe(true)
  })
})
```

(Nota: a versão anterior deste teste mockava `global.fetch` + `await Promise.resolve()`
duas vezes pra deixar a promise do threshold resolver antes de disparar a mensagem SSE.
A Task 1 reproduziu e confirmou que isso falha deterministicamente — a cadeia real
`fetch → authFetchJson → getThreshold → .then` precisa de 4 microtasks, não 2. Reescrito
pra mockar `realMetaApi.getThreshold` direto via `vi.spyOn` — 1 `await Promise.resolve()`
basta, e a integração `metaApi → authFetchJson → fetch` que esse mock "esconde" já está
coberta em `metaApi.test.ts`/`http.test.ts`. Isola em `liveApi.test.ts` só o que é
responsabilidade do adapter: URL, cache de threshold, cálculo de `alarm_state`,
`unsubscribe`.)

- [ ] **Step 4: Rodar o teste e confirmar que falha**

Run: `npx vitest run src/lib/api/real/liveApi.test.ts`
Expected: falha — `Failed to resolve import "./liveApi"` (arquivo ainda não existe).

- [ ] **Step 5: Criar `frontend/src/lib/api/real/liveApi.ts`**

```ts
import type { LiveApi } from '../contracts'
import type { AlarmState, Threshold } from '../../types'
import { TOKEN_STORAGE_KEY } from '../../useAuth'
import { computeStatus } from '../../status'
import { BASE_URL } from './http'
import { realMetaApi } from './metaApi'

export const realLiveApi: LiveApi = {
  subscribe(sensor_code, cb) {
    let threshold: Threshold | null = null
    realMetaApi.getThreshold(sensor_code).then((t) => { threshold = t }).catch(() => {})

    const token = localStorage.getItem(TOKEN_STORAGE_KEY)
    const es = new EventSource(`${BASE_URL}/sensores/${sensor_code}/live?token=${token}`)
    es.onmessage = (event) => {
      const { time, valor } = JSON.parse(event.data)
      const { state } = computeStatus(valor, threshold)
      const alarm_state: AlarmState = state === 'unknown' ? 'ok' : state
      cb({ sensor_code, ts: time, value: valor, alarm_state })
    }
    return () => es.close()
  },
}
```

- [ ] **Step 6: Rodar o teste e confirmar que passa**

Run: `npx vitest run src/lib/api/real/liveApi.test.ts`
Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/api/real/http.ts frontend/src/lib/api/real/liveApi.ts frontend/src/lib/api/real/liveApi.test.ts
git commit -m "feat: realLiveApi (EventSource + threshold cacheado + alarm_state local)"
```

---

## Task 2: Ligar `liveApi` ao switch `VITE_API_MODE` + verificação final

**Files:**
- Modify: `frontend/src/lib/api/index.ts`

**Interfaces:**
- Consumes: `realLiveApi: LiveApi` (Task 1).
- Produces: `index.ts` exportando os 4 adapters (`authApi`/`metaApi`/`historyApi`/`liveApi`) todos ligados ao mesmo switch `VITE_API_MODE`.

- [ ] **Step 1: Atualizar `frontend/src/lib/api/index.ts`** — trocar

```ts
import type { MetaApi, HistoryApi, LiveApi, AuthApi } from './contracts'
import { mockMetaApi } from './mock/metaApi'
import { mockHistoryApi } from './mock/historyApi'
import { mockLiveApi } from './mock/liveApi'
import { mockAuthApi } from './mock/authApi'
import { realAuthApi } from './real/authApi'
import { realMetaApi } from './real/metaApi'
import { realHistoryApi } from './real/historyApi'

// Fase 3 (real) entra aqui sem tocar componentes: authApi/metaApi/historyApi
// ja tem impl real (ver frontend/CONTRACTS.md) -- liveApi ainda nao (sem
// backend SSE).
const mode = import.meta.env.VITE_API_MODE ?? 'mock'
if (mode === 'real') {
  console.info(
    'VITE_API_MODE=real: authApi/metaApi/historyApi reais; liveApi ainda mock (sem backend SSE)',
  )
} else if (mode !== 'mock') {
  console.warn(`VITE_API_MODE=${mode} nao reconhecido; usando mock para todos os adapters`)
}

export const authApi: AuthApi = mode === 'real' ? realAuthApi : mockAuthApi
export const metaApi: MetaApi = mode === 'real' ? realMetaApi : mockMetaApi
export const historyApi: HistoryApi = mode === 'real' ? realHistoryApi : mockHistoryApi
export const liveApi: LiveApi = mockLiveApi
```

por

```ts
import type { MetaApi, HistoryApi, LiveApi, AuthApi } from './contracts'
import { mockMetaApi } from './mock/metaApi'
import { mockHistoryApi } from './mock/historyApi'
import { mockLiveApi } from './mock/liveApi'
import { mockAuthApi } from './mock/authApi'
import { realAuthApi } from './real/authApi'
import { realMetaApi } from './real/metaApi'
import { realHistoryApi } from './real/historyApi'
import { realLiveApi } from './real/liveApi'

// Fase 3 (real) entra aqui sem tocar componentes: os 4 adapters ja tem impl
// real (ver frontend/CONTRACTS.md).
const mode = import.meta.env.VITE_API_MODE ?? 'mock'
if (mode === 'real') {
  console.info('VITE_API_MODE=real: todos os adapters reais (auth/meta/history/live)')
} else if (mode !== 'mock') {
  console.warn(`VITE_API_MODE=${mode} nao reconhecido; usando mock para todos os adapters`)
}

export const authApi: AuthApi = mode === 'real' ? realAuthApi : mockAuthApi
export const metaApi: MetaApi = mode === 'real' ? realMetaApi : mockMetaApi
export const historyApi: HistoryApi = mode === 'real' ? realHistoryApi : mockHistoryApi
export const liveApi: LiveApi = mode === 'real' ? realLiveApi : mockLiveApi
```

- [ ] **Step 2: Rodar a suíte completa do frontend**

Run (a partir de `frontend/`): `npm test`
Expected: todos os testes passam (suite existente + 5 novos de `liveApi.test.ts`).

- [ ] **Step 3: Rodar o build (typecheck + bundle)**

Run: `npm run build`
Expected: sem erros de TypeScript, build completa.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api/index.ts
git commit -m "feat: liga liveApi ao switch VITE_API_MODE"
```

- [ ] **Step 5: Commit final de verificação**

```bash
git add -A
git commit -m "chore: verificacao final do adapter real liveApi" --allow-empty
```
