# Adapters reais: metaApi + historyApi — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trocar `mockMetaApi`/`mockHistoryApi` por adapters reais (`realMetaApi`/`realHistoryApi`) que chamam a API FastAPI (`api/meta.py`, `api/historico.py`, já em `master`), plugados no mesmo switch `VITE_API_MODE` que já liga `realAuthApi`.

**Architecture:** Um helper novo, `frontend/src/lib/api/real/http.ts` (`authFetchJson<T>(path)`), compartilhado pelos dois adapters — lê o token de `localStorage`, monta o header `Authorization: Bearer`, faz `fetch`, lança em resposta não-`ok`, senão devolve `res.json()`. `realMetaApi`/`realHistoryApi` ficam finos, cada método é uma chamada a `authFetchJson`.

**Tech Stack:** React + TypeScript, Vitest (`environment: 'jsdom'`, `globals: true`), `vi.stubGlobal('fetch', ...)` para mockar rede — mesmo padrão já usado em `frontend/src/lib/api/real/authApi.test.ts`.

## Global Constraints

- `BASE_URL` = `import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001'` — mesmo padrão de `real/authApi.ts`.
- Toda resposta não-`ok` (401, 404, 500...) vira `throw new Error(...)` genérico — sem diferenciação por status, sem logout automático (fora de escopo).
- `getThreshold`: resposta `200` com corpo `null` é repassada como está (sensor existe, sem threshold configurado); resposta `404` (sensor inexistente) cai no `throw` genérico — mesmo comportamento que `mockMetaApi.getThreshold` já tem hoje.
- A chave de storage do token (`'sentinela_token'`) só pode existir em um lugar — exportada de `useAuth.tsx`, nunca duplicada como string literal em outro arquivo.
- `liveApi` continua mock — sem backend SSE ainda, fora de escopo deste plano.
- Testes rodam sempre com `VITE_API_MODE=mock` forçado por `vite.config.ts` (`test.env`), então nenhum teste deste plano depende do valor real de `VITE_API_MODE` — o switch em `index.ts` é só lido, não testado isoladamente (mesmo padrão do switch de `authApi`, que também não tem teste próprio).

---

## Task 1: Helper `authFetchJson` + export da chave de storage

**Files:**
- Modify: `frontend/src/lib/useAuth.tsx`
- Create: `frontend/src/lib/api/real/http.ts`
- Test: `frontend/src/lib/api/real/http.test.ts`

**Interfaces:**
- Consumes: nada de tasks anteriores.
- Produces: `authFetchJson<T>(path: string): Promise<T>` (usado pelas Tasks 2 e 3); `TOKEN_STORAGE_KEY: string` exportado de `useAuth.tsx` (usado por `http.ts`).

- [ ] **Step 1: Exportar a chave de storage em `useAuth.tsx`**

Arquivo atual (`frontend/src/lib/useAuth.tsx`) tem:

```ts
const STORAGE_KEY = 'sentinela_token'
```

e usa `STORAGE_KEY` em 4 lugares (`readValidToken`, `login`, `logout`). Trocar a declaração por:

```ts
export const TOKEN_STORAGE_KEY = 'sentinela_token'
```

E renomear as 4 ocorrências de `STORAGE_KEY` no resto do arquivo para `TOKEN_STORAGE_KEY`. O arquivo final deve ficar assim:

```tsx
import { createContext, useContext, useState, type ReactNode } from 'react'
import { authApi } from './api'
import { decodeJwtExp } from './jwt'

export const TOKEN_STORAGE_KEY = 'sentinela_token'

type AuthContextValue = {
  isAuthenticated: boolean
  login: (usuario: string, senha: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

function readValidToken(): string | null {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  if (!token) return null
  const exp = decodeJwtExp(token)
  if (exp === null || exp <= Date.now()) {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
    return null
  }
  return token
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => readValidToken())

  async function login(usuario: string, senha: string) {
    const { access_token } = await authApi.login(usuario, senha)
    localStorage.setItem(TOKEN_STORAGE_KEY, access_token)
    setToken(access_token)
  }

  function logout() {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
    setToken(null)
  }

  return (
    <AuthContext.Provider value={{ isAuthenticated: token !== null, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth precisa estar dentro de AuthProvider')
  return ctx
}
```

- [ ] **Step 2: Rodar a suíte pra confirmar que o rename não quebrou nada**

Run (a partir de `frontend/`): `npx vitest run src/lib`
Expected: todos os testes existentes de `src/lib` continuam passando (o rename é interno, nada externo referencia `STORAGE_KEY`).

- [ ] **Step 3: Escrever o teste em `frontend/src/lib/api/real/http.test.ts`**

```ts
import { describe, it, expect, vi, afterEach } from 'vitest'
import { authFetchJson } from './http'
import { TOKEN_STORAGE_KEY } from '../../useAuth'

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('authFetchJson', () => {
  it('inclui Authorization: Bearer quando ha token em localStorage', async () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'abc.def.ghi')
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ foo: 'bar' }) })
    vi.stubGlobal('fetch', mockFetch)

    const result = await authFetchJson('/sensores/SNR-1')

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/sensores/SNR-1'),
      { headers: { Authorization: 'Bearer abc.def.ghi' } },
    )
    expect(result).toEqual({ foo: 'bar' })
  })

  it('sem token em localStorage, chama sem header Authorization', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
    vi.stubGlobal('fetch', mockFetch)

    await authFetchJson('/sensores')

    expect(mockFetch).toHaveBeenCalledWith(expect.any(String), { headers: {} })
  })

  it('resposta nao-ok lanca erro', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({}) }))
    await expect(authFetchJson('/sensores/SNR-X')).rejects.toThrow()
  })
})
```

- [ ] **Step 4: Rodar o teste e confirmar que falha**

Run: `npx vitest run src/lib/api/real/http.test.ts`
Expected: falha — `Failed to resolve import "./http"` (arquivo ainda não existe).

- [ ] **Step 5: Criar `frontend/src/lib/api/real/http.ts`**

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

- [ ] **Step 6: Rodar o teste e confirmar que passa**

Run: `npx vitest run src/lib/api/real/http.test.ts`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/useAuth.tsx frontend/src/lib/api/real/http.ts frontend/src/lib/api/real/http.test.ts
git commit -m "feat: helper authFetchJson + exporta TOKEN_STORAGE_KEY de useAuth"
```

---

## Task 2: `realMetaApi`

**Files:**
- Create: `frontend/src/lib/api/real/metaApi.ts`
- Test: `frontend/src/lib/api/real/metaApi.test.ts`

**Interfaces:**
- Consumes: `authFetchJson<T>(path: string): Promise<T>` (Task 1); tipo `MetaApi` de `frontend/src/lib/api/contracts.ts` (`getSensor(code): Promise<SensorMeta>`, `getThreshold(code): Promise<Threshold | null>`, `listSensors(): Promise<SensorMeta[]>`).
- Produces: `realMetaApi: MetaApi` (usado pela Task 3 ao ligar o switch em `index.ts`).

- [ ] **Step 1: Escrever o teste em `frontend/src/lib/api/real/metaApi.test.ts`**

```ts
import { describe, it, expect, vi, afterEach } from 'vitest'
import { realMetaApi } from './metaApi'

afterEach(() => vi.unstubAllGlobals())

const SENSOR = {
  sensor_code: 'SNR-1',
  name: 'Sensor 1',
  unidade: 'C',
  protocolo_origem: '4-20ma',
  measurement_type: { code: 'TEMP', name: 'Temperatura' },
  area: { area_code: 'AREA-1', name: 'Expurgo', category: 'CME' },
}

describe('realMetaApi', () => {
  it('getSensor chama GET /sensores/{code} e devolve o JSON', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => SENSOR })
    vi.stubGlobal('fetch', mockFetch)

    const result = await realMetaApi.getSensor('SNR-1')

    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/sensores/SNR-1'), expect.anything())
    expect(result).toEqual(SENSOR)
  })

  it('getThreshold chama GET /sensores/{code}/threshold e devolve o JSON (podendo ser null)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => null }))

    const result = await realMetaApi.getThreshold('SNR-SEM-THRESHOLD')

    expect(result).toBeNull()
  })

  it('getThreshold com sensor inexistente (404) lanca erro', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({}) }))

    await expect(realMetaApi.getThreshold('SNR-NAO-EXISTE')).rejects.toThrow()
  })

  it('listSensors chama GET /sensores e devolve a lista', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [SENSOR] })
    vi.stubGlobal('fetch', mockFetch)

    const result = await realMetaApi.listSensors()

    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/sensores'), expect.anything())
    expect(result).toEqual([SENSOR])
  })
})
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `npx vitest run src/lib/api/real/metaApi.test.ts`
Expected: falha — `Failed to resolve import "./metaApi"` (arquivo ainda não existe).

- [ ] **Step 3: Criar `frontend/src/lib/api/real/metaApi.ts`**

```ts
import type { MetaApi } from '../contracts'
import { authFetchJson } from './http'

export const realMetaApi: MetaApi = {
  getSensor(code) {
    return authFetchJson(`/sensores/${code}`)
  },
  getThreshold(code) {
    return authFetchJson(`/sensores/${code}/threshold`)
  },
  listSensors() {
    return authFetchJson('/sensores')
  },
}
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `npx vitest run src/lib/api/real/metaApi.test.ts`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api/real/metaApi.ts frontend/src/lib/api/real/metaApi.test.ts
git commit -m "feat: realMetaApi (getSensor/getThreshold/listSensors)"
```

---

## Task 3: `realHistoryApi` + ligar o switch `VITE_API_MODE` + verificação final

**Files:**
- Create: `frontend/src/lib/api/real/historyApi.ts`
- Test: `frontend/src/lib/api/real/historyApi.test.ts`
- Modify: `frontend/src/lib/api/index.ts`

**Interfaces:**
- Consumes: `authFetchJson<T>(path: string): Promise<T>` (Task 1); tipo `HistoryApi` de `contracts.ts` (`getHistory(code, window): Promise<HistoryResponse>`); `realMetaApi` (Task 2); `realAuthApi` (já existente).
- Produces: `realHistoryApi: HistoryApi`; `index.ts` exportando `metaApi`/`historyApi`/`authApi` todos ligados ao mesmo switch `VITE_API_MODE`.

- [ ] **Step 1: Escrever o teste em `frontend/src/lib/api/real/historyApi.test.ts`**

```ts
import { describe, it, expect, vi, afterEach } from 'vitest'
import { realHistoryApi } from './historyApi'

afterEach(() => vi.unstubAllGlobals())

describe('realHistoryApi', () => {
  it('getHistory chama GET /sensores/{code}/historico?window={window} e devolve o JSON', async () => {
    const body = {
      sensor_code: 'SNR-1',
      window: '1h',
      resolution: 'raw',
      points: [{ ts: 1700000000000, value: 20.1 }],
    }
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => body })
    vi.stubGlobal('fetch', mockFetch)

    const result = await realHistoryApi.getHistory('SNR-1', '1h')

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/sensores/SNR-1/historico?window=1h'),
      expect.anything(),
    )
    expect(result).toEqual(body)
  })
})
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `npx vitest run src/lib/api/real/historyApi.test.ts`
Expected: falha — `Failed to resolve import "./historyApi"` (arquivo ainda não existe).

- [ ] **Step 3: Criar `frontend/src/lib/api/real/historyApi.ts`**

```ts
import type { HistoryApi } from '../contracts'
import { authFetchJson } from './http'

export const realHistoryApi: HistoryApi = {
  getHistory(code, window) {
    return authFetchJson(`/sensores/${code}/historico?window=${window}`)
  },
}
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

Run: `npx vitest run src/lib/api/real/historyApi.test.ts`
Expected: 1 passed.

- [ ] **Step 5: Atualizar `frontend/src/lib/api/index.ts`** — trocar

```ts
import type { MetaApi, HistoryApi, LiveApi, AuthApi } from './contracts'
import { mockMetaApi } from './mock/metaApi'
import { mockHistoryApi } from './mock/historyApi'
import { mockLiveApi } from './mock/liveApi'
import { mockAuthApi } from './mock/authApi'
import { realAuthApi } from './real/authApi'

// Fase 3 (real) entra aqui sem tocar componentes: authApi ja tem impl real
// (ver frontend/CONTRACTS.md §5) -- metaApi/historyApi/liveApi ainda nao.
const mode = import.meta.env.VITE_API_MODE ?? 'mock'
if (mode === 'real') {
  console.info(
    'VITE_API_MODE=real: authApi real; metaApi/historyApi/liveApi ainda mock (adapters reais nao implementados nesta fatia)',
  )
} else if (mode !== 'mock') {
  console.warn(`VITE_API_MODE=${mode} nao reconhecido; usando mock para todos os adapters`)
}

export const authApi: AuthApi = mode === 'real' ? realAuthApi : mockAuthApi
export const metaApi: MetaApi = mockMetaApi
export const historyApi: HistoryApi = mockHistoryApi
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

- [ ] **Step 6: Rodar a suíte completa do frontend**

Run (a partir de `frontend/`): `npm test`
Expected: todos os testes passam (suite existente + 3 novos de `http.test.ts` + 4 novos de `metaApi.test.ts` + 1 novo de `historyApi.test.ts` = 8 testes novos).

- [ ] **Step 7: Rodar o build (typecheck + bundle) pra garantir que nada quebrou tipagem**

Run: `npm run build`
Expected: sem erros de TypeScript, build completa.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/api/real/historyApi.ts frontend/src/lib/api/real/historyApi.test.ts frontend/src/lib/api/index.ts
git commit -m "feat: realHistoryApi + liga metaApi/historyApi ao switch VITE_API_MODE"
```

- [ ] **Step 9: Commit final de verificação**

```bash
git add -A
git commit -m "chore: verificacao final dos adapters reais metaApi/historyApi" --allow-empty
```
