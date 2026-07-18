# Frontend Sentinela CME — Roteamento: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Conectar `OverviewPage` (`/`) e `SensorDetailPage` (`/sensor/:code`) via `react-router`, com navegação real (clicar num cartão de área → Detalhe do Sensor; link "Voltar" → Overview).

**Architecture:** `react-router` (`BrowserRouter`+`Routes`+`Route`) em `App.tsx`. `SensorDetailPage` mantém sua assinatura `{code: string}` inalterada — um wrapper local (`SensorRoute`) lê `useParams` e repassa. `AreaCard` vira um `Link` pro sensor da área. Nenhum componente de página muda de responsabilidade, só ganha navegação.

**Tech Stack:** `react-router` (novo). Resto igual ao já estabelecido (Vite, React 19, TS, Tailwind v4, TanStack Query, Vitest + Testing Library; testes com router usam `MemoryRouter`).

## Global Constraints

- **Local:** `frontend/` dentro do worktree `/home/afonso/docker/odoo_sentinela/.worktrees/frontend-overview` (branch `feat/frontend-overview-iso`). Não tocar nada fora deste worktree.
- **Sem mudança de design visual** além do necessário para indicar interatividade (hover/foco no cartão agora clicável).
- **`SensorDetailPage` não muda de assinatura** (`{code: string}`) — só quem a invoca muda.
- **Escopo:** 1 sensor por área (hoje) → cartão navega direto pro único sensor da área, sem tela intermediária de escolha.
- TDD, commits frequentes.

---

## File Structure

```
frontend/
├── package.json                        # MODIFICA: + react-router
└── src/
    ├── App.tsx                          # MODIFICA: BrowserRouter + Routes
    ├── App.test.tsx                     # NOVO: rotas renderizam a pagina certa
    ├── components/
    │   ├── AreaCard.tsx                 # MODIFICA: vira Link
    │   └── AreaCard.test.tsx            # MODIFICA: wrap em MemoryRouter
    └── pages/
        ├── SensorDetailPage.tsx         # MODIFICA: + link "Voltar"
        ├── SensorDetailPage.test.tsx    # MODIFICA: wrap em MemoryRouter
        └── OverviewPage.test.tsx        # MODIFICA: wrap em MemoryRouter (AreaCard agora e Link)
```

---

### Task 1: Instalar react-router + rotas em `App.tsx`

**Files:**
- Modify: `frontend/package.json` (via `npm install`)
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/App.test.tsx`

**Interfaces:**
- Produces: rota `/` renderiza `OverviewPage`; rota `/sensor/:code` renderiza `SensorDetailPage` com o `code` do param da URL (via um wrapper local `SensorRoute`).

- [ ] **Step 1: Instalar dependência**

```bash
cd /home/afonso/docker/odoo_sentinela/.worktrees/frontend-overview/frontend
npm install react-router
```

- [ ] **Step 2: Escrever teste (falha)**

`frontend/src/App.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import type { ReactNode } from 'react'

vi.mock('echarts', () => ({ init: () => ({ setOption: vi.fn(), dispose: vi.fn(), resize: vi.fn() }) }))

import App from './App'

function wrap(node: ReactNode, initialPath: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>{node}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('App routing', () => {
  it('"/" renderiza a Overview', async () => {
    render(wrap(<App />, '/'))
    await waitFor(() => expect(screen.getByText('Visão geral')).toBeInTheDocument())
  })

  it('"/sensor/:code" renderiza o Detalhe do sensor certo', async () => {
    render(wrap(<App />, '/sensor/TEMP-EXP-01'))
    await waitFor(() => expect(screen.getByText(/Temperatura — Expurgo/)).toBeInTheDocument())
  })
})
```

Nota: `App.tsx` hoje NÃO inclui `QueryClientProvider` (isso fica em `main.tsx`) — o teste acima o adiciona manualmente, igual ao padrão já usado em `OverviewPage.test.tsx`/`SensorDetailPage.test.tsx`. `App.tsx`, depois deste task, passa a incluir `BrowserRouter` internamente — mas o teste usa `MemoryRouter` diretamente envolvendo `<App/>`, o que exigiria dois routers aninhados se `App.tsx` também tiver `BrowserRouter`. Para evitar isso, `App.tsx` deste task **não** inclui o `BrowserRouter` — ele continua vivendo em `main.tsx` (Step 4), e `App.tsx` só define `Routes`/`Route`. Isso também é mais correto: `main.tsx` é quem decide o tipo de router (browser real em produção, memory em teste).

- [ ] **Step 3: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/App.test.tsx`
Expected: FAIL — `App.tsx` ainda não tem rotas (`Visão geral` está lá por acaso, sempre renderizado; mas `/sensor/TEMP-EXP-01` não vai renderizar `SensorDetailPage`).

- [ ] **Step 4: Implementar rotas**

Substituir `frontend/src/App.tsx`:

```tsx
import { Routes, Route, useParams } from 'react-router'
import { OverviewPage } from './pages/OverviewPage'
import { SensorDetailPage } from './pages/SensorDetailPage'

function SensorRoute() {
  const { code } = useParams<{ code: string }>()
  return <SensorDetailPage code={code!} />
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<OverviewPage />} />
      <Route path="/sensor/:code" element={<SensorRoute />} />
    </Routes>
  )
}
```

Editar `frontend/src/main.tsx` — envolver `<App />` com `BrowserRouter`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router'
import App from './App.tsx'
import './index.css'

const qc = new QueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
```

- [ ] **Step 5: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/App.test.tsx`
Expected: PASS — 2 testes.

Run: `cd frontend && npm test`
Expected: PASS — suite completa (nenhuma regressão; `OverviewPage.test.tsx`/`SensorDetailPage.test.tsx` renderizam os componentes diretamente, sem passar por `App`, então não são afetados por esta task ainda — serão atualizados nas Tasks 2 e 3 quando `AreaCard`/`SensorDetailPage` ganharem `Link`s).

- [ ] **Step 6: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela/.worktrees/frontend-overview
git add frontend/package.json frontend/package-lock.json frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/main.tsx
git commit -m "feat(frontend): react-router — rotas / (Overview) e /sensor/:code (Detalhe)"
```

---

### Task 2: `AreaCard` vira link navegável

**Files:**
- Modify: `frontend/src/components/AreaCard.tsx`
- Modify: `frontend/src/components/AreaCard.test.tsx`
- Modify: `frontend/src/pages/OverviewPage.test.tsx` (wrap em `MemoryRouter`, já que `AreaCard` passa a exigir contexto de router)

**Interfaces:**
- Produces: `AreaCard` renderiza como `Link` (react-router) pro `/sensor/<code do unico sensor da area>`.

- [ ] **Step 1: Atualizar `AreaCard.test.tsx` (envolver em `MemoryRouter`) e adicionar teste de navegação (falha)**

Substituir `frontend/src/components/AreaCard.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { AreaCard } from './AreaCard'
import type { AreaGroup } from '../lib/aggregateStatus'
import type { LivePoint, Threshold } from '../lib/types'

function wrap(node: React.ReactNode) {
  return <MemoryRouter>{node}</MemoryRouter>
}

const expurgo: AreaGroup = {
  area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Refrigeração' },
  sensors: [{
    sensor_code: 'TEMP-EXP-01', name: 'Temperatura', unidade: 'C', protocolo_origem: 'rs485',
    measurement_type: { code: 'temperatura', name: 'Temperatura' },
    area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Refrigeração' },
  }],
}
const t: Threshold = { sensor_id: 'TEMP-EXP-01', limite_min: 18, limite_max: 22, is_valor_padrao_regulatorio: true }

describe('AreaCard', () => {
  it('mostra nome e categoria da area', () => {
    render(wrap(<AreaCard group={expurgo} thresholdsByCode={{ 'TEMP-EXP-01': t }} liveByCode={{}} />))
    expect(screen.getByText('Expurgo')).toBeInTheDocument()
  })

  it('e um link pro sensor da area', () => {
    render(wrap(<AreaCard group={expurgo} thresholdsByCode={{ 'TEMP-EXP-01': t }} liveByCode={{}} />))
    expect(screen.getByRole('link')).toHaveAttribute('href', '/sensor/TEMP-EXP-01')
  })

  it('sensor ok: mostra "Dentro da faixa", sem badge de alarme', () => {
    const live: LivePoint = { sensor_code: 'TEMP-EXP-01', ts: 1, value: 20, alarm_state: 'ok' }
    render(wrap(<AreaCard group={expurgo} thresholdsByCode={{ 'TEMP-EXP-01': t }} liveByCode={{ 'TEMP-EXP-01': live }} />))
    expect(screen.getByText('Dentro da faixa')).toBeInTheDocument()
    expect(screen.queryByText(/alarme/i)).not.toBeInTheDocument()
  })

  it('sensor crit: mostra "Fora da faixa" E badge "1 alarme"', () => {
    const live: LivePoint = { sensor_code: 'TEMP-EXP-01', ts: 1, value: 30, alarm_state: 'crit' }
    render(wrap(<AreaCard group={expurgo} thresholdsByCode={{ 'TEMP-EXP-01': t }} liveByCode={{ 'TEMP-EXP-01': live }} />))
    expect(screen.getByText('Fora da faixa')).toBeInTheDocument()
    expect(screen.getByText('1 alarme')).toBeInTheDocument()
  })

  it('sensor sem threshold (Arsenal): mostra "Sem limite", mesmo com feed ok', () => {
    const arsenal: AreaGroup = {
      area: { area_code: 'ARSENAL', name: 'Arsenal', category: 'Armazenamento' },
      sensors: [{
        sensor_code: 'TEMP-ARS-01', name: 'Temperatura', unidade: 'C', protocolo_origem: 'rs485',
        measurement_type: { code: 'temperatura', name: 'Temperatura' },
        area: { area_code: 'ARSENAL', name: 'Arsenal', category: 'Armazenamento' },
      }],
    }
    const live: LivePoint = { sensor_code: 'TEMP-ARS-01', ts: 1, value: 24, alarm_state: 'ok' }
    render(wrap(<AreaCard group={arsenal} thresholdsByCode={{ 'TEMP-ARS-01': null }} liveByCode={{ 'TEMP-ARS-01': live }} />))
    expect(screen.getByText('Sem limite')).toBeInTheDocument()
  })

  it('status sempre vem com icone (nao so cor) — svg presente junto ao texto', () => {
    const live: LivePoint = { sensor_code: 'TEMP-EXP-01', ts: 1, value: 30, alarm_state: 'crit' }
    const { container } = render(
      wrap(<AreaCard group={expurgo} thresholdsByCode={{ 'TEMP-EXP-01': t }} liveByCode={{ 'TEMP-EXP-01': live }} />),
    )
    expect(container.querySelector('svg')).not.toBeNull()
  })
})
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/components/AreaCard.test.tsx`
Expected: FAIL — sem `MemoryRouter` real uso de `Link` ainda, o teste "e um link" falha (nenhum elemento com role `link`); os demais devem continuar passando (regressão zero nos que já existiam), já que só envolver em `MemoryRouter` não muda o markup atual.

- [ ] **Step 3: Implementar — `AreaCard` vira `Link`**

Substituir `frontend/src/components/AreaCard.tsx`:

```tsx
import { Link } from 'react-router'
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
    <Link
      to={`/sensor/${group.sensors[0].sensor_code}`}
      className="block rounded-2xl p-5 outline-none transition-colors duration-200 ease-out hover:border-[var(--color-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
      style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}
      data-testid={`area-card-${group.area.area_code}`}
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
    </Link>
  )
}
```

Nota: `<Link>` renderiza um `<a>` — `data-testid`/estilos de card continuam funcionando igual (só trocou a tag raiz de `div` pra link). O hover usa `border-[var(--color-primary)]` (token existente, sem cor nova).

- [ ] **Step 4: Atualizar `OverviewPage.test.tsx` — envolver em `MemoryRouter`**

Em `frontend/src/pages/OverviewPage.test.tsx`, adicionar o import e trocar a função `wrap`:

```tsx
import { MemoryRouter } from 'react-router'
```

```tsx
function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>
  )
}
```

(Resto do arquivo permanece igual — `AreaCard` agora precisa de contexto de router pra renderizar sem lançar erro, e `MemoryRouter` fornece isso sem navegar de verdade.)

- [ ] **Step 5: Rodar testes (devem passar)**

Run: `cd frontend && npx vitest run src/components/AreaCard.test.tsx src/pages/OverviewPage.test.tsx`
Expected: PASS — todos.

Run: `cd frontend && npm test`
Expected: PASS — suite completa.

- [ ] **Step 6: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela/.worktrees/frontend-overview
git add frontend/src/components/AreaCard.tsx frontend/src/components/AreaCard.test.tsx frontend/src/pages/OverviewPage.test.tsx
git commit -m "feat(frontend): AreaCard vira link navegavel pro sensor da area"
```

---

### Task 3: Link "Voltar" no `SensorDetailPage`

**Files:**
- Modify: `frontend/src/pages/SensorDetailPage.tsx`
- Modify: `frontend/src/pages/SensorDetailPage.test.tsx` (wrap em `MemoryRouter`)

**Interfaces:**
- Produces: `SensorDetailPage` renderiza um `Link` pro `/` no header, antes do título.

- [ ] **Step 1: Atualizar `SensorDetailPage.test.tsx` — envolver em `MemoryRouter` + teste do link**

Em `frontend/src/pages/SensorDetailPage.test.tsx`, adicionar o import:

```tsx
import { MemoryRouter } from 'react-router'
```

Trocar a função `wrap`:

```tsx
function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>
  )
}
```

Adicionar um novo teste ao final do `describe`:

```tsx
  it('tem link "Voltar" pra Overview', async () => {
    render(wrap(<SensorDetailPage code="TEMP-EXP-01" />))
    await waitFor(() => expect(screen.getByText(/Temperatura — Expurgo/)).toBeInTheDocument())
    expect(screen.getByRole('link', { name: /voltar/i })).toHaveAttribute('href', '/')
  })
```

- [ ] **Step 2: Rodar teste (deve falhar)**

Run: `cd frontend && npx vitest run src/pages/SensorDetailPage.test.tsx`
Expected: FAIL — teste novo falha (link "Voltar" ainda não existe); os demais continuam passando (envolver em `MemoryRouter` não muda comportamento existente).

- [ ] **Step 3: Implementar — adicionar link "Voltar" no header**

Em `frontend/src/pages/SensorDetailPage.tsx`, adicionar o import no topo:

```tsx
import { Link } from 'react-router'
```

E editar o `<header>` — trocar:

```tsx
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
```

por:

```tsx
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <Link
            to="/"
            className="mb-2 inline-flex items-center gap-1 text-sm font-medium outline-none transition-colors duration-200 ease-out hover:text-[var(--color-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
            style={{ color: 'var(--color-muted)' }}
          >
            ← Voltar
          </Link>
```

(A tag `<div>` de abertura some da versão nova porque já foi movida pra dentro do bloco acima — o restante do conteúdo do `<div>` original, o `{meta.isLoading ? ... }` do título e subtítulo, continua exatamente igual logo depois do `<Link>`, ainda dentro da mesma `<div>`.)

- [ ] **Step 4: Rodar teste (deve passar)**

Run: `cd frontend && npx vitest run src/pages/SensorDetailPage.test.tsx`
Expected: PASS — todos.

Run: `cd frontend && npm test`
Expected: PASS — suite completa. `npm run build` limpo.

- [ ] **Step 5: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela/.worktrees/frontend-overview
git add frontend/src/pages/SensorDetailPage.tsx frontend/src/pages/SensorDetailPage.test.tsx
git commit -m "feat(frontend): link Voltar no Detalhe do Sensor -> Overview"
```

---

### Task 4: Teste de integração — fluxo completo de navegação

**Files:**
- Modify: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: `App` (com as rotas + `AreaCard`/`SensorDetailPage` já navegáveis das Tasks 2-3).

- [ ] **Step 1: Adicionar teste de fluxo (falha)**

Adicionar ao final do `describe('App routing', ...)` em `frontend/src/App.test.tsx`:

```tsx
  it('clicar num cartao da Overview navega pro Detalhe, e Voltar retorna', async () => {
    render(wrap(<App />, '/'))
    await waitFor(() => expect(screen.getByText('Expurgo')).toBeInTheDocument(), { timeout: 3000 })

    await userEvent.click(screen.getByTestId('area-card-EXPURGO'))
    await waitFor(() => expect(screen.getByText(/Temperatura — Expurgo/)).toBeInTheDocument())

    await userEvent.click(screen.getByRole('link', { name: /voltar/i }))
    await waitFor(() => expect(screen.getByText('Visão geral')).toBeInTheDocument())
  })
```

Adicionar os imports que faltam no topo do arquivo (`userEvent`, se ainda não importado):

```tsx
import userEvent from '@testing-library/user-event'
```

- [ ] **Step 2: Rodar teste (deve falhar, se algo na navegação estiver quebrado — senão já passa direto por reaproveitar Tasks 1-3)**

Run: `cd frontend && npx vitest run src/App.test.tsx`
Expected: se as Tasks 1-3 foram implementadas corretamente, este teste já deve passar de primeira (é um teste de integração das peças já prontas, não introduz comportamento novo) — confirmar isso é o próprio propósito do teste. Se falhar, investigar qual das 3 tasks anteriores tem um problema de integração antes de prosseguir.

- [ ] **Step 3: Rodar suite completa + build**

Run: `cd frontend && npm test`
Expected: PASS — suite completa.

Run: `cd frontend && npm run build`
Expected: build limpo.

- [ ] **Step 4: Verificação visual real (browser)**

Rodar `npm run dev`, abrir no browser: confirmar que clicar num cartão da Overview navega de verdade pro Detalhe do Sensor (URL muda pra `/sensor/...`), o link "Voltar" funciona, o cartão mostra hover/foco visível ao passar o mouse/tab, e nada quebrou visualmente nas duas telas (mesma checagem de light/dark já feita nas fatias anteriores).

- [ ] **Step 5: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela/.worktrees/frontend-overview
git add frontend/src/App.test.tsx
git commit -m "test(frontend): fluxo de navegacao completo Overview <-> Detalhe do Sensor"
```

---

## Self-Review

**Spec coverage:** §2 lib (react-router) → Task 1. §3 rotas → Task 1. §4 navegação (AreaCard Link, botão Voltar) → Tasks 2, 3. §5 wiring (App.tsx/main.tsx) → Task 1. §6 testes 1-3 → Tasks 2, 1, 4. §7 entregáveis → todas + verificação visual (Task 4, Step 4).

**Placeholder scan:** sem TBD/TODO; todo passo tem código completo.

**Type consistency:** `AreaCard`/`OverviewPage`/`SensorDetailPage` mantêm suas assinaturas de props inalteradas (só ganham `Link`/contexto de router). `SensorRoute` é a única peça nova de tipo, local a `App.tsx`, não exportada (não precisa de teste próprio — coberta pelos testes de integração de `App.test.tsx`).

**Risco assumido:** `AreaCard`/`SensorDetailPage` passam a exigir um `Router` ancestral pra renderizar sem lançar erro (`Link`/`useParams` fora de contexto de router lança). Todos os testes desses componentes são atualizados nas Tasks 2-3 para envolver em `MemoryRouter` — nenhum teste fica órfão.
