# Frontend Sentinela CME — Login: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tela de login que autentica contra a API real (`POST /auth/login`, Fase 3, já implementada no backend), guarda o JWT, protege as rotas existentes atrás de um guard, e oferece logout.

**Architecture:** Reusa o seam mock/real já estabelecido (`lib/api/`) — `authApi` ganha `mockAuthApi` (padrão do projeto, credencial `admin`/`admin`, token genuinamente formatado como JWT) e `realAuthApi` (chama a API de verdade via `fetch`), selecionados por `VITE_API_MODE`. Estado de auth em Context React + `localStorage` (sem lib nova). `AuthGuard` é uma rota-pai do react-router (`<Outlet/>`) envolvendo as 3 rotas já existentes.

**Tech Stack:** Igual ao já estabelecido — Vite, React 19, TS, Tailwind v4, TanStack Query, react-router, Vitest + Testing Library. Nenhuma dependência nova.

## Global Constraints

- **Local:** `frontend/` dentro do worktree `/home/afonso/docker/odoo_sentinela/.worktrees/login` (branch `feat/frontend-login`). Não tocar nada fora deste worktree — checkout principal é compartilhado com outra sessão.
- **`metaApi`/`historyApi`/`liveApi` continuam mockados** — fora de escopo. Só `authApi` ganha implementação real nesta fatia.
- **Resposta real de `POST /auth/login`**: `{access_token: string, token_type: 'bearer'}` — sem nome/partner_id solto (ficam dentro do JWT, opacos pro frontend).
- **Mocks usam base de tempo fixa** (não `Date.now()`), mesma convenção já usada em `liveApi.ts`/`historyApi.ts` — mantém testes determinísticos.
- **Decode de JWT client-side nunca verifica assinatura** — só lê `exp` pra saber quando encerrar a sessão local; validação de verdade é sempre no servidor.
- TDD, commits frequentes.

---

## File Structure

```
frontend/
├── .env.local                          # NOVO, nao versionado (*.local no .gitignore): VITE_API_MODE=real p/ testar contra a API de verdade
└── src/
    ├── App.tsx                          # MODIFICA: + rota /login + AuthGuard envolvendo as 3 rotas existentes
    ├── App.test.tsx                     # MODIFICA: seed de token nos testes existentes (senao quebram com o guard) + novo teste de fluxo completo de auth
    ├── main.tsx                         # MODIFICA: + AuthProvider envolvendo <App/>
    ├── lib/
    │   ├── jwt.ts                        # NOVO: decodeJwtExp
    │   ├── jwt.test.ts                   # NOVO
    │   ├── useAuth.tsx                   # NOVO: AuthProvider + useAuth()
    │   ├── useAuth.test.tsx              # NOVO
    │   └── api/
    │       ├── contracts.ts              # MODIFICA: + AuthApi
    │       ├── index.ts                  # MODIFICA: seleciona authApi por VITE_API_MODE
    │       ├── mock/
    │       │   ├── authApi.ts             # NOVO
    │       │   └── authApi.test.ts        # NOVO
    │       └── real/
    │           ├── authApi.ts             # NOVO
    │           └── authApi.test.ts        # NOVO
    ├── pages/
    │   ├── LoginPage.tsx                 # NOVO
    │   └── LoginPage.test.tsx            # NOVO
    └── components/
        ├── AuthGuard.tsx                 # NOVO
        ├── AuthGuard.test.tsx             # NOVO
        ├── LogoutButton.tsx               # NOVO
        └── HeaderActions.tsx              # NOVO: agrupa ThemeToggle + LogoutButton (substitui o uso solto de ThemeToggle nas 3 paginas)
```

`OverviewPage.tsx`, `AreaPage.tsx`, `SensorDetailPage.tsx` — modificados na Task 5 (trocar `<ThemeToggle/>` solto por `<HeaderActions/>`).

---

### Task 1: `lib/jwt.ts` — decode de expiração (sem verificar assinatura)

**Files:**
- Create: `frontend/src/lib/jwt.ts`
- Create: `frontend/src/lib/jwt.test.ts`

**Interfaces:**
- Produces: `decodeJwtExp(token: string): number | null` — devolve o `exp` do payload em **milissegundos** (o JWT guarda em segundos Unix), ou `null` se o token for malformado/sem `exp`. Nunca lança.

- [ ] **Step 1: Escrever testes (falha)**

`frontend/src/lib/jwt.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { decodeJwtExp } from './jwt'

function b64url(obj: object): string {
  return btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function makeJwt(payload: object): string {
  return `${b64url({ alg: 'HS256', typ: 'JWT' })}.${b64url(payload)}.fake-signature`
}

describe('decodeJwtExp', () => {
  it('decodifica exp de um JWT valido (segundos -> ms)', () => {
    const token = makeJwt({ sub: '2', partner_id: 3, exp: 1784399777 })
    expect(decodeJwtExp(token)).toBe(1784399777 * 1000)
  })

  it('decodifica um JWT REAL emitido pela API (Fase 3, capturado via curl)', () => {
    const real =
      'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyIiwicGFydG5lcl9pZCI6MywiZXhwIjoxNzg0Mzk5Nzc3fQ.uAEPdegFf2aPpqX-eLPRwb7GaE6u1psq0RH9M_B1Bw4'
    expect(decodeJwtExp(real)).toBe(1784399777 * 1000)
  })

  it('token malformado (sem 3 segmentos) devolve null, nao lanca', () => {
    expect(decodeJwtExp('nao-e-um-jwt')).toBeNull()
  })

  it('payload sem exp devolve null', () => {
    const token = makeJwt({ sub: '2' })
    expect(decodeJwtExp(token)).toBeNull()
  })

  it('payload nao-JSON valido devolve null, nao lanca', () => {
    expect(decodeJwtExp('abc.###.def')).toBeNull()
  })
})
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/lib/jwt.test.ts`
Expected: FAIL — `./jwt` não existe.

- [ ] **Step 3: Implementar**

`frontend/src/lib/jwt.ts`:

```ts
// Decodifica so o payload de um JWT (base64url, 2o segmento) pra ler `exp`.
// NAO verifica assinatura -- isso e responsabilidade do servidor a cada
// request autenticada. Uso client-side e so pra saber quando encerrar a
// sessao local (nao e um controle de seguranca).
export function decodeJwtExp(token: string): number | null {
  const parts = token.split('.')
  if (parts.length !== 3) return null
  try {
    const payloadB64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const json = atob(payloadB64)
    const payload = JSON.parse(json) as { exp?: number }
    if (typeof payload.exp !== 'number') return null
    return payload.exp * 1000 // segundos -> ms
  } catch {
    return null
  }
}
```

- [ ] **Step 4: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/lib/jwt.test.ts`
Expected: PASS — todos os 5.

- [ ] **Step 5: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela/.worktrees/login
git add frontend/src/lib/jwt.ts frontend/src/lib/jwt.test.ts
git commit -m "feat(frontend): decodeJwtExp — le expiracao do JWT sem verificar assinatura"
```

---

### Task 2: `AuthApi` — contrato + `mockAuthApi` + `realAuthApi`

**Files:**
- Modify: `frontend/src/lib/api/contracts.ts`
- Modify: `frontend/src/lib/api/index.ts`
- Create: `frontend/src/lib/api/mock/authApi.ts`
- Create: `frontend/src/lib/api/mock/authApi.test.ts`
- Create: `frontend/src/lib/api/real/authApi.ts`
- Create: `frontend/src/lib/api/real/authApi.test.ts`

**Interfaces:**
- Consumes: `decodeJwtExp` (Task 1, só usado nos testes desta task pra confirmar o token do mock é JWT-shaped).
- Produces: `AuthApi = { login(usuario: string, senha: string): Promise<{access_token: string; token_type: string}> }`. `authApi` exportado de `lib/api/index.ts`, selecionado por `VITE_API_MODE` (`'real'` → `realAuthApi`; qualquer outro valor, incluindo ausente → `mockAuthApi`).

- [ ] **Step 1: Escrever testes (falha) — `mockAuthApi`**

`frontend/src/lib/api/mock/authApi.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { mockAuthApi } from './authApi'
import { decodeJwtExp } from '../../jwt'

describe('mockAuthApi', () => {
  it('admin/admin devolve token JWT-shaped (3 segmentos) com exp no futuro (base fixa + 3600s)', async () => {
    const { access_token, token_type } = await mockAuthApi.login('admin', 'admin')
    expect(token_type).toBe('bearer')
    expect(access_token.split('.')).toHaveLength(3)
    expect(decodeJwtExp(access_token)).toBe((1_700_000_000 + 3600) * 1000)
  })

  it('credencial errada rejeita', async () => {
    await expect(mockAuthApi.login('admin', 'errada')).rejects.toThrow()
  })

  it('usuario desconhecido rejeita', async () => {
    await expect(mockAuthApi.login('outro', 'admin')).rejects.toThrow()
  })
})
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/lib/api/mock/authApi.test.ts`
Expected: FAIL — `./authApi` não existe.

- [ ] **Step 3: Estender `contracts.ts`**

Em `frontend/src/lib/api/contracts.ts`, adicionar ao final:

```ts
export type AuthApi = {
  login(usuario: string, senha: string): Promise<{ access_token: string; token_type: string }>
}
```

- [ ] **Step 4: Implementar `mockAuthApi`**

`frontend/src/lib/api/mock/authApi.ts`:

```ts
import type { AuthApi } from '../contracts'

// Mesma convencao das outras fixtures mock (liveApi.ts/historyApi.ts): base
// de tempo fixa, nao Date.now(), pra manter os testes deterministicos.
const MOCK_ISSUED_AT_S = 1_700_000_000
const EXP_SECONDS = 3600

// Formato JWT genuino (3 segmentos base64url) mesmo sendo mock -- assim
// decodeJwtExp funciona identico pro mock e pro real, sem logica duplicada.
// A "assinatura" e so um placeholder de texto -- nada verifica ela no mock.
function b64url(obj: object): string {
  return btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function makeFakeJwt(): string {
  const header = { alg: 'HS256', typ: 'JWT' }
  const payload = { sub: '1', partner_id: 1, exp: MOCK_ISSUED_AT_S + EXP_SECONDS }
  return `${b64url(header)}.${b64url(payload)}.mock-signature-nao-verificada`
}

export const mockAuthApi: AuthApi = {
  async login(usuario, senha) {
    // Mesma credencial de teste que a API real (Fase 3) usa -- ensina a
    // credencial certa pra quando acoplar de verdade.
    if (usuario !== 'admin' || senha !== 'admin') {
      throw new Error('credenciais inválidas')
    }
    return { access_token: makeFakeJwt(), token_type: 'bearer' }
  },
}
```

- [ ] **Step 5: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/lib/api/mock/authApi.test.ts`
Expected: PASS — todos os 3.

- [ ] **Step 6: Escrever testes (falha) — `realAuthApi`**

`frontend/src/lib/api/real/authApi.test.ts`:

```ts
import { describe, it, expect, vi, afterEach } from 'vitest'
import { realAuthApi } from './authApi'

afterEach(() => vi.unstubAllGlobals())

describe('realAuthApi', () => {
  it('POST /auth/login com body {usuario,senha}, devolve o JSON da resposta em sucesso', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: 'abc.def.ghi', token_type: 'bearer' }),
    })
    vi.stubGlobal('fetch', mockFetch)

    const result = await realAuthApi.login('admin', 'admin')

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/auth/login'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ usuario: 'admin', senha: 'admin' }),
      }),
    )
    expect(result).toEqual({ access_token: 'abc.def.ghi', token_type: 'bearer' })
  })

  it('resposta nao-ok (ex: 401) lanca erro', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) }))
    await expect(realAuthApi.login('admin', 'errada')).rejects.toThrow()
  })
})
```

- [ ] **Step 7: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/lib/api/real/authApi.test.ts`
Expected: FAIL — `./authApi` não existe.

- [ ] **Step 8: Implementar `realAuthApi`**

`frontend/src/lib/api/real/authApi.ts`:

```ts
import type { AuthApi } from '../contracts'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001'

export const realAuthApi: AuthApi = {
  async login(usuario, senha) {
    const res = await fetch(`${BASE_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ usuario, senha }),
    })
    if (!res.ok) {
      throw new Error('credenciais inválidas')
    }
    return res.json()
  },
}
```

- [ ] **Step 9: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/lib/api/real/authApi.test.ts`
Expected: PASS — todos os 2.

- [ ] **Step 10: Ligar `authApi` no seletor**

Substituir `frontend/src/lib/api/index.ts`:

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
if (mode !== 'mock') {
  console.info(
    `VITE_API_MODE=${mode}: authApi real; metaApi/historyApi/liveApi ainda mock (adapters reais nao implementados nesta fatia)`,
  )
}

export const authApi: AuthApi = mode === 'real' ? realAuthApi : mockAuthApi
export const metaApi: MetaApi = mockMetaApi
export const historyApi: HistoryApi = mockHistoryApi
export const liveApi: LiveApi = mockLiveApi
```

- [ ] **Step 11: Rodar suite completa**

Run: `cd frontend && npm test`
Expected: PASS — suite completa (nenhuma regressão; nada ainda consome `authApi` fora dos testes desta task).

- [ ] **Step 12: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela/.worktrees/login
git add frontend/src/lib/api/contracts.ts frontend/src/lib/api/index.ts frontend/src/lib/api/mock/authApi.ts frontend/src/lib/api/mock/authApi.test.ts frontend/src/lib/api/real/authApi.ts frontend/src/lib/api/real/authApi.test.ts
git commit -m "feat(frontend): AuthApi (mock + real) — login contra a API de verdade quando VITE_API_MODE=real"
```

---

### Task 3: `lib/useAuth.tsx` — `AuthProvider` + `useAuth()`

**Files:**
- Create: `frontend/src/lib/useAuth.tsx`
- Create: `frontend/src/lib/useAuth.test.tsx`

**Interfaces:**
- Consumes: `authApi` (`lib/api/index.ts`, Task 2), `decodeJwtExp` (`lib/jwt.ts`, Task 1).
- Produces: `AuthProvider({children}): JSX.Element`, `useAuth(): {isAuthenticated: boolean; login(usuario: string, senha: string): Promise<void>; logout(): void}`. Chave do `localStorage`: `'sentinela_token'`.

- [ ] **Step 1: Escrever testes (falha)**

`frontend/src/lib/useAuth.test.tsx`:

```tsx
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AuthProvider, useAuth } from './useAuth'

function b64url(obj: object): string {
  return btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function Probe() {
  const { isAuthenticated, login, logout } = useAuth()
  return (
    <div>
      <span data-testid="status">{isAuthenticated ? 'dentro' : 'fora'}</span>
      <button onClick={() => login('admin', 'admin')}>entrar</button>
      <button onClick={() => logout()}>sair</button>
    </div>
  )
}

beforeEach(() => localStorage.clear())

describe('AuthProvider/useAuth', () => {
  it('comeca deslogado sem token no storage', () => {
    render(<AuthProvider><Probe /></AuthProvider>)
    expect(screen.getByTestId('status')).toHaveTextContent('fora')
  })

  it('login com credencial certa guarda token e fica autenticado', async () => {
    render(<AuthProvider><Probe /></AuthProvider>)
    await userEvent.click(screen.getByText('entrar'))
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('dentro'))
    expect(localStorage.getItem('sentinela_token')).not.toBeNull()
  })

  it('logout limpa o token e volta a deslogado', async () => {
    render(<AuthProvider><Probe /></AuthProvider>)
    await userEvent.click(screen.getByText('entrar'))
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('dentro'))
    await userEvent.click(screen.getByText('sair'))
    expect(screen.getByTestId('status')).toHaveTextContent('fora')
    expect(localStorage.getItem('sentinela_token')).toBeNull()
  })

  it('token expirado no storage ja nasce deslogado (e limpa o storage)', () => {
    const expired = `${b64url({ alg: 'HS256' })}.${b64url({ exp: 1_700_000_000 })}.sig` // base fixa, bem no passado
    localStorage.setItem('sentinela_token', expired)
    render(<AuthProvider><Probe /></AuthProvider>)
    expect(screen.getByTestId('status')).toHaveTextContent('fora')
    expect(localStorage.getItem('sentinela_token')).toBeNull()
  })
})
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/lib/useAuth.test.tsx`
Expected: FAIL — `./useAuth` não existe.

- [ ] **Step 3: Implementar**

`frontend/src/lib/useAuth.tsx`:

```tsx
import { createContext, useContext, useState, type ReactNode } from 'react'
import { authApi } from './api'
import { decodeJwtExp } from './jwt'

const STORAGE_KEY = 'sentinela_token'

type AuthContextValue = {
  isAuthenticated: boolean
  login: (usuario: string, senha: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

function readValidToken(): string | null {
  const token = localStorage.getItem(STORAGE_KEY)
  if (!token) return null
  const exp = decodeJwtExp(token)
  if (exp === null || exp <= Date.now()) {
    localStorage.removeItem(STORAGE_KEY)
    return null
  }
  return token
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => readValidToken())

  async function login(usuario: string, senha: string) {
    const { access_token } = await authApi.login(usuario, senha)
    localStorage.setItem(STORAGE_KEY, access_token)
    setToken(access_token)
  }

  function logout() {
    localStorage.removeItem(STORAGE_KEY)
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

- [ ] **Step 4: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/lib/useAuth.test.tsx`
Expected: PASS — todos os 4.

Run: `cd frontend && npm test`
Expected: PASS — suite completa.

- [ ] **Step 5: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela/.worktrees/login
git add frontend/src/lib/useAuth.tsx frontend/src/lib/useAuth.test.tsx
git commit -m "feat(frontend): AuthProvider/useAuth — estado de sessao em Context + localStorage"
```

---

### Task 4: `LoginPage` + `AuthGuard` + rota `/login` + wiring

**Files:**
- Create: `frontend/src/pages/LoginPage.tsx`
- Create: `frontend/src/pages/LoginPage.test.tsx`
- Create: `frontend/src/components/AuthGuard.tsx`
- Create: `frontend/src/components/AuthGuard.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: `useAuth` (`lib/useAuth.tsx`, Task 3).
- Produces: `<LoginPage/>` (usuário/senha, chama `useAuth().login`, navega pra `/` em sucesso). `<AuthGuard/>` (rota-pai `<Outlet/>`, redireciona pra `/login` se `!isAuthenticated`).

- [ ] **Step 1: Escrever testes (falha) — `AuthGuard`**

`frontend/src/components/AuthGuard.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router'
import { AuthProvider } from '../lib/useAuth'
import { AuthGuard } from './AuthGuard'

function b64url(obj: object): string {
  return btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function wrap(initialPath: string) {
  return (
    <AuthProvider>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/login" element={<div>tela de login</div>} />
          <Route element={<AuthGuard />}>
            <Route path="/" element={<div>pagina protegida</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthProvider>
  )
}

describe('AuthGuard', () => {
  it('sem autenticacao redireciona pra /login', () => {
    localStorage.clear()
    render(wrap('/'))
    expect(screen.getByText('tela de login')).toBeInTheDocument()
    expect(screen.queryByText('pagina protegida')).not.toBeInTheDocument()
  })

  it('com token valido no storage, renderiza a rota protegida', () => {
    const valid = `${b64url({ alg: 'HS256' })}.${b64url({ exp: Math.floor(Date.now() / 1000) + 3600 })}.sig`
    localStorage.setItem('sentinela_token', valid)
    render(wrap('/'))
    expect(screen.getByText('pagina protegida')).toBeInTheDocument()
    localStorage.clear()
  })
})
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/components/AuthGuard.test.tsx`
Expected: FAIL — `./AuthGuard` não existe.

- [ ] **Step 3: Implementar `AuthGuard`**

`frontend/src/components/AuthGuard.tsx`:

```tsx
import { Navigate, Outlet } from 'react-router'
import { useAuth } from '../lib/useAuth'

export function AuthGuard() {
  const { isAuthenticated } = useAuth()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <Outlet />
}
```

- [ ] **Step 4: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/components/AuthGuard.test.tsx`
Expected: PASS — todos os 2.

- [ ] **Step 5: Escrever testes (falha) — `LoginPage`**

`frontend/src/pages/LoginPage.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router'
import { AuthProvider } from '../lib/useAuth'
import { LoginPage } from './LoginPage'

function wrap() {
  return (
    <AuthProvider>
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<div>pagina protegida</div>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>
  )
}

describe('LoginPage', () => {
  it('credencial certa navega pra /', async () => {
    localStorage.clear()
    render(wrap())
    await userEvent.type(screen.getByLabelText('Usuário'), 'admin')
    await userEvent.type(screen.getByLabelText('Senha'), 'admin')
    await userEvent.click(screen.getByRole('button', { name: /entrar/i }))
    await waitFor(() => expect(screen.getByText('pagina protegida')).toBeInTheDocument())
  })

  it('credencial errada mostra erro, nao navega', async () => {
    localStorage.clear()
    render(wrap())
    await userEvent.type(screen.getByLabelText('Usuário'), 'admin')
    await userEvent.type(screen.getByLabelText('Senha'), 'errada')
    await userEvent.click(screen.getByRole('button', { name: /entrar/i }))
    await waitFor(() => expect(screen.getByText(/usuário ou senha inválidos/i)).toBeInTheDocument())
    expect(screen.queryByText('pagina protegida')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 6: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/pages/LoginPage.test.tsx`
Expected: FAIL — `./LoginPage` não existe.

- [ ] **Step 7: Implementar `LoginPage`**

`frontend/src/pages/LoginPage.tsx`:

```tsx
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { useAuth } from '../lib/useAuth'

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [usuario, setUsuario] = useState('')
  const [senha, setSenha] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [carregando, setCarregando] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setErro(null)
    setCarregando(true)
    try {
      await login(usuario, senha)
      navigate('/')
    } catch {
      setErro('Usuário ou senha inválidos.')
    } finally {
      setCarregando(false)
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-sm flex-col justify-center p-4">
      <h1 className="mb-6 text-xl font-bold" style={{ color: 'var(--color-ink)' }}>
        Sentinela CME
      </h1>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="usuario" className="mb-1 block text-sm font-medium" style={{ color: 'var(--color-muted)' }}>
            Usuário
          </label>
          <input
            id="usuario"
            type="text"
            value={usuario}
            onChange={(e) => setUsuario(e.target.value)}
            className="min-h-11 w-full rounded-md px-3 text-sm outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
            style={{ border: '1px solid var(--color-line)', color: 'var(--color-ink)', background: 'var(--color-surface)' }}
            autoComplete="username"
          />
        </div>
        <div>
          <label htmlFor="senha" className="mb-1 block text-sm font-medium" style={{ color: 'var(--color-muted)' }}>
            Senha
          </label>
          <input
            id="senha"
            type="password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            className="min-h-11 w-full rounded-md px-3 text-sm outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
            style={{ border: '1px solid var(--color-line)', color: 'var(--color-ink)', background: 'var(--color-surface)' }}
            autoComplete="current-password"
          />
        </div>
        {erro && (
          <p className="text-sm font-semibold" style={{ color: 'var(--color-crit)' }}>
            {erro}
          </p>
        )}
        <button
          type="submit"
          disabled={carregando}
          className="min-h-11 w-full rounded-md text-sm font-semibold text-[var(--color-surface)] outline-none transition-colors duration-200 ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] disabled:opacity-60 motion-reduce:transition-none"
          style={{ background: 'var(--color-primary)' }}
        >
          {carregando ? 'Entrando…' : 'Entrar'}
        </button>
      </form>
    </div>
  )
}
```

- [ ] **Step 8: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/pages/LoginPage.test.tsx`
Expected: PASS — todos os 2.

- [ ] **Step 9: Wiring — `main.tsx` (AuthProvider) e `App.tsx` (rota /login + guard)**

Substituir `frontend/src/main.tsx`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router'
import { AuthProvider } from './lib/useAuth'
import App from './App.tsx'
import './index.css'

const qc = new QueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
```

Substituir `frontend/src/App.tsx`:

```tsx
import { Routes, Route, useParams } from 'react-router'
import { OverviewPage } from './pages/OverviewPage'
import { SensorDetailPage } from './pages/SensorDetailPage'
import { AreaPage } from './pages/AreaPage'
import { LoginPage } from './pages/LoginPage'
import { AuthGuard } from './components/AuthGuard'

function SensorRoute() {
  const { code } = useParams<{ code: string }>()
  return <SensorDetailPage code={code!} />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<AuthGuard />}>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/area/:areaCode" element={<AreaPage />} />
        <Route path="/sensor/:code" element={<SensorRoute />} />
      </Route>
    </Routes>
  )
}
```

- [ ] **Step 10: Atualizar `App.test.tsx`** — os testes existentes navegam direto pra `/`/`/sensor/...` sem logar; com o guard agora em vigor, quebrariam. Semear um token válido antes de cada teste (e envolver em `AuthProvider`, que faltava) resolve, sem mudar o que cada teste verifica:

Substituir `frontend/src/App.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'

vi.mock('echarts', () => ({ init: () => ({ setOption: vi.fn(), dispose: vi.fn(), resize: vi.fn() }) }))

import App from './App'
import { AuthProvider } from './lib/useAuth'

function b64url(obj: object): string {
  return btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function seedValidToken() {
  const token = `${b64url({ alg: 'HS256' })}.${b64url({ exp: Math.floor(Date.now() / 1000) + 3600 })}.sig`
  localStorage.setItem('sentinela_token', token)
}

function wrap(node: ReactNode, initialPath: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <AuthProvider>{node}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => seedValidToken())
afterEach(() => localStorage.clear())

describe('App routing', () => {
  it('"/" renderiza a Overview', async () => {
    render(wrap(<App />, '/'))
    await waitFor(() => expect(screen.getByText('Visão geral')).toBeInTheDocument())
  })

  it('"/sensor/:code" renderiza o Detalhe do sensor certo', async () => {
    render(wrap(<App />, '/sensor/TEMP-EXP-01'))
    await waitFor(() => expect(screen.getByText(/Temperatura — Expurgo/)).toBeInTheDocument())
  })

  it('fluxo completo: Overview -> Area -> Sensor -> Voltar -> Overview', async () => {
    render(wrap(<App />, '/'))
    await waitFor(() => expect(screen.getByText('Expurgo')).toBeInTheDocument(), { timeout: 3000 })

    await userEvent.click(screen.getByTestId('area-card-EXPURGO'))
    await waitFor(() => expect(screen.getByText('Pressão diferencial')).toBeInTheDocument(), { timeout: 3000 })

    await userEvent.click(screen.getByText('Temperatura'))
    await waitFor(() => expect(screen.getByText(/Temperatura — Expurgo/)).toBeInTheDocument())

    await userEvent.click(screen.getByRole('link', { name: /voltar/i }))
    await waitFor(() => expect(screen.getByText('Visão geral')).toBeInTheDocument(), { timeout: 3000 })
  })
})
```

- [ ] **Step 11: Rodar suite completa**

Run: `cd frontend && npm test`
Expected: PASS — suite completa. Se algum dos 3 testes de `App.test.tsx` que já existiam falhar, investigar antes de prosseguir — não é esperado (o seed de token deve bastar).

- [ ] **Step 12: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela/.worktrees/login
git add frontend/src/pages/LoginPage.tsx frontend/src/pages/LoginPage.test.tsx frontend/src/components/AuthGuard.tsx frontend/src/components/AuthGuard.test.tsx frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/main.tsx
git commit -m "feat(frontend): LoginPage + AuthGuard + rota /login protegendo as demais"
```

---

### Task 5: Logout — `LogoutButton` + `HeaderActions`, wiring nas 3 páginas, fluxo completo

**Files:**
- Create: `frontend/src/components/LogoutButton.tsx`
- Create: `frontend/src/components/HeaderActions.tsx`
- Modify: `frontend/src/pages/OverviewPage.tsx`
- Modify: `frontend/src/pages/AreaPage.tsx`
- Modify: `frontend/src/pages/SensorDetailPage.tsx`
- Modify: `frontend/src/App.test.tsx`
- Create: `frontend/.env.local` (não versionado)

**Interfaces:**
- Consumes: `useAuth` (Task 3), `ThemeToggle` (já existente).
- Produces: `<LogoutButton/>`, `<HeaderActions/>` (agrupa `ThemeToggle`+`LogoutButton`, substitui o `<ThemeToggle/>` solto nas 3 páginas).

- [ ] **Step 1: Implementar `LogoutButton`** (sem TDD isolado — comportamento coberto pelo teste de integração do Step 6; é um botão simples que chama `logout()`+navega)

`frontend/src/components/LogoutButton.tsx`:

```tsx
import { useNavigate } from 'react-router'
import { useAuth } from '../lib/useAuth'

export function LogoutButton() {
  const { logout } = useAuth()
  const navigate = useNavigate()

  function handleClick() {
    logout()
    navigate('/login')
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      className="flex min-h-11 items-center gap-2 rounded-md px-3 py-1.5 text-sm font-semibold outline-none transition-colors duration-200 ease-out hover:text-[var(--color-crit)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
      style={{ border: '1px solid var(--color-line)', color: 'var(--color-muted)' }}
    >
      Sair
    </button>
  )
}
```

- [ ] **Step 2: Implementar `HeaderActions`**

`frontend/src/components/HeaderActions.tsx`:

```tsx
import { ThemeToggle } from './ThemeToggle'
import { LogoutButton } from './LogoutButton'

export function HeaderActions() {
  return (
    <div className="flex items-center gap-2">
      <ThemeToggle />
      <LogoutButton />
    </div>
  )
}
```

- [ ] **Step 3: Trocar `<ThemeToggle/>` por `<HeaderActions/>` nas 3 páginas**

Em `frontend/src/pages/OverviewPage.tsx`: trocar o import
```ts
import { ThemeToggle } from '../components/ThemeToggle'
```
por
```ts
import { HeaderActions } from '../components/HeaderActions'
```
e trocar o uso `<ThemeToggle />` por `<HeaderActions />`.

Em `frontend/src/pages/AreaPage.tsx`: mesma troca (import de `ThemeToggle` → `HeaderActions`, uso `<ThemeToggle />` → `<HeaderActions />`).

Em `frontend/src/pages/SensorDetailPage.tsx`: mesma troca.

- [ ] **Step 4: Rodar suite completa (deve passar — nada mudou de comportamento visível de auth ainda, só o botão apareceu)**

Run: `cd frontend && npm test`
Expected: PASS — suite completa.

- [ ] **Step 5: Escrever o teste de fluxo completo de auth (falha até o Step 3 acima estar correto — mas como já implementamos tudo, roda GREEN direto; confirmar mesmo assim)**

Adicionar ao final do `describe('App routing', ...)` em `frontend/src/App.test.tsx`:

```tsx
  it('fluxo completo de auth: sem login redireciona, loga, navega, desloga, bloqueia de novo', async () => {
    localStorage.clear() // sobrescreve o beforeEach (que semeia token valido) -- comeca deslogado de proposito
    render(wrap(<App />, '/'))

    // sem token, tentar acessar / redireciona pra tela de login
    await waitFor(() => expect(screen.getByLabelText('Usuário')).toBeInTheDocument())

    await userEvent.type(screen.getByLabelText('Usuário'), 'admin')
    await userEvent.type(screen.getByLabelText('Senha'), 'admin')
    await userEvent.click(screen.getByRole('button', { name: /entrar/i }))

    // login ok, entra na Overview
    await waitFor(() => expect(screen.getByText('Visão geral')).toBeInTheDocument(), { timeout: 3000 })

    // desloga
    await userEvent.click(screen.getByRole('button', { name: /sair/i }))

    // volta pra tela de login, e o token sumiu do storage
    await waitFor(() => expect(screen.getByLabelText('Usuário')).toBeInTheDocument())
    expect(localStorage.getItem('sentinela_token')).toBeNull()
  })
```

- [ ] **Step 6: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/App.test.tsx`
Expected: PASS — todos.

Run: `cd frontend && npm test`
Expected: PASS — suite completa.

Run: `cd frontend && npm run build`
Expected: build limpo.

- [ ] **Step 7: Criar `.env.local` (não versionado — já coberto por `*.local` no `.gitignore`) pra testar contra a API real**

`frontend/.env.local`:

```
VITE_API_MODE=real
VITE_API_BASE_URL=http://localhost:8001
```

Confirmar que `git status` **não** lista este arquivo como staged/rastreável (`*.local` já está no `.gitignore` de `frontend/`).

- [ ] **Step 8: Verificação visual real (browser) — login de verdade contra a API rodando**

Confirmar a API real está no ar (`curl http://localhost:8001/health` deve responder `{"status":"ok"}` — se não estiver, subir com `python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8001` a partir da raiz do repo principal, não deste worktree). Rodar `npm run dev`, abrir no browser:
1. Acessar `/` sem login → redireciona pra `/login`.
2. Logar com `admin`/`admin` → entra na Overview de verdade (dados continuam mock, só o login é real).
3. Logar com senha errada → mensagem de erro, sem navegar.
4. Clicar "Sair" → volta pro login, tentar acessar `/` de novo → bloqueado.
5. Conferir light/dark no formulário de login (mesma disciplina de toda fatia anterior — 3 das 4 fatias anteriores acharam bug real só nesta etapa).

- [ ] **Step 9: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela/.worktrees/login
git add frontend/src/components/LogoutButton.tsx frontend/src/components/HeaderActions.tsx frontend/src/pages/OverviewPage.tsx frontend/src/pages/AreaPage.tsx frontend/src/pages/SensorDetailPage.tsx frontend/src/App.test.tsx
git commit -m "feat(frontend): logout (HeaderActions nas 3 paginas) + fluxo completo de auth testado"
```

(`.env.local` não é adicionado ao commit — não versionado, de propósito.)

---

## Self-Review

**Spec coverage:** §2 contrato (`AuthApi`) → Task 2 + `CONTRACTS.md` já atualizado no commit de design. §3 seam mock/real → Task 2. §4 estado (`decodeJwtExp`, `useAuth`) → Tasks 1, 3. §5 rotas/guard → Task 4. §6 componentes (`LoginPage`, botão de logout) → Tasks 4, 5. §7 testes 1-6 → Task 1 (1), Task 2 (2), Task 3 (3), Task 4 (4, 5), Task 5 (6). §8 entregáveis → todas as tasks + `.env.local` (Task 5) + verificação visual (Task 5).

**Placeholder scan:** sem TBD/TODO; todo passo tem código completo.

**Type consistency:** `AuthApi.login` mesma assinatura em `contracts.ts`, `mockAuthApi`, `realAuthApi`, e no uso de `useAuth.tsx`. Chave de storage `'sentinela_token'` idêntica em `useAuth.tsx` e em todos os testes que semeiam/leem o storage diretamente (Tasks 3, 4, 5). `decodeJwtExp` mesma assinatura em Task 1 e nos dois usos (Task 2 teste, Task 3 implementação).

**Risco assumido e mitigado:** os 3 testes pré-existentes de `App.test.tsx` (roteamento sem auth) quebrariam com o guard — a Task 4 já corrige isso semeando token válido, não deixado para depois. A Task 5 adiciona o teste que cobre o caminho inverso (sem token → bloqueado) para não perder essa cobertura.

**Nota sobre verificação visual:** obrigatória (Task 5, Step 8) — as 3 fatias anteriores acharam bug real (gráfico vazio, cor errada, hover morto, `ThemeToggle` ausente) só nessa etapa, nunca em testes automatizados. Login é a primeira tela nova desde então; não pular.
