# Dashboard Editor — Polish de UX — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refinar a usabilidade do editor de dashboard customizável em 5 pontos: controles/título no gráfico temporal, widgets responsivos ao card, handle de resize visível no dark, adicionar card por drag-and-drop, e popover de config ancorado ao botão.

**Architecture:** Frontend SPA React 19 + Vite 8 + Tailwind v4. Widgets renderizados por `WIDGET_REGISTRY` dentro de `WidgetFrame`, posicionados por `react-grid-layout` (`DashboardGrid`), editados via `DashboardEditor`. As mudanças ficam nessas peças + CSS global + 2 deps novas (`@floating-ui/react`, `@playwright/test`).

**Tech Stack:** React 19.2, Vite 8, Tailwind v4.3 (@container), react-grid-layout 1.5.3, @floating-ui/react, ECharts, TanStack Query, Vitest+jsdom, Playwright.

## Global Constraints

- Responder/comentar código em português (identificadores em inglês ok).
- `@floating-ui/react` é a única dep de runtime nova; `@playwright/test` é dev-only.
- Tailwind v4: container queries via `@container` no elemento pai + variantes `@sm:`/`@md:` nos filhos.
- Baseline de testes: 213/214 (a falha `demoMode` é pré-existente e é corrigida na Task 0).
- react-grid-layout já é React-19-compatível (passa `nodeRef`); NÃO reabrir esse tema.
- Cada task termina com suite verde e commit. Verificação visual (Playwright, light+dark) é o critério de aceite de UX/design/layout — chrome-devtools MCP não sobe no WSL2.
- Não rodar `npx playwright install` de browsers sem necessidade; usar o Chrome/Chromium já presente se possível (`channel: 'chrome'` ou executablePath), senão instalar só chromium.

---

### Task 0: Setup — deps, fix demoMode, harness de screenshot, baseline

**Files:**
- Modify: `frontend/package.json` (deps)
- Modify: `frontend/vite.config.ts` (test env)
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/shot.spec.ts` (harness de screenshot do editor)
- Create: `frontend/e2e/helpers.ts` (login admin + entrar em modo edição)

**Interfaces:**
- Produces: helper `loginAndEnterEdit(page)` reutilizável; script `npm run shot` que gera screenshots light+dark do dashboard e do editor em `e2e/__shots__/`.

- [ ] **Step 1: Instalar deps**

Run: `cd frontend && npm i @floating-ui/react && npm i -D @playwright/test`
Expected: instala sem erro; `@floating-ui/react` em dependencies.

- [ ] **Step 2: Corrigir teste demoMode pré-existente**

Modify `frontend/vite.config.ts`, no bloco `test.env`:

```ts
env: { VITE_API_MODE: 'mock', VITE_DEMO_MODE: '' },
```

Run: `npx vitest run src/lib/demoMode.test.ts`
Expected: PASS (antes falhava por `.env.local` ter `VITE_DEMO_MODE=true`).

- [ ] **Step 3: playwright.config.ts**

```ts
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  use: {
    baseURL: 'http://localhost:5173',
    channel: 'chrome', // usa o Chrome do sistema; evita download de browser
    viewport: { width: 1440, height: 900 },
  },
})
```

- [ ] **Step 4: e2e/helpers.ts**

```ts
import type { Page } from '@playwright/test'

// Login admin real (backend FastAPI :8001, user admin do profile odoo-sentinela)
// depende de ADMIN_PW no env do processo de teste.
export async function loginAndEnterEdit(page: Page) {
  await page.goto('/')
  // Se cair na tela de login, autentica.
  if (await page.getByLabel(/usu[aá]rio/i).count()) {
    await page.getByLabel(/usu[aá]rio/i).fill('admin')
    await page.getByLabel(/senha/i).fill(process.env.ADMIN_PW ?? '')
    await page.getByRole('button', { name: /entrar/i }).click()
  }
  await page.getByRole('button', { name: 'Editar' }).click()
}
```

(Ajustar seletores aos labels reais de `LoginPage.tsx` — o implementador deve
abrir o arquivo e casar os `aria-label`/textos.)

- [ ] **Step 5: e2e/shot.spec.ts (harness reutilizável)**

```ts
import { test } from '@playwright/test'
import { loginAndEnterEdit } from './helpers'

for (const theme of ['claro', 'escuro'] as const) {
  test(`editor screenshot ${theme}`, async ({ page }) => {
    await loginAndEnterEdit(page)
    // ThemeToggle: botão "Claro"/"Escuro" na topbar
    const wanted = theme === 'escuro' ? /escuro|dark/i : /claro|light/i
    const toggle = page.getByRole('button', { name: wanted })
    if (await toggle.count()) await toggle.first().click()
    await page.waitForTimeout(400)
    await page.screenshot({ path: `e2e/__shots__/editor-${theme}.png`, fullPage: true })
  })
}
```

- [ ] **Step 6: script npm**

Modify `frontend/package.json` scripts: `"shot": "playwright test e2e/shot.spec.ts"`.

- [ ] **Step 7: Gerar baseline**

Run (backend :8001 e vite :5173 devem estar de pé): `ADMIN_PW=<senha> npm run shot`
Expected: `e2e/__shots__/editor-claro.png` e `editor-escuro.png` gerados. Anexar/inspecionar.

- [ ] **Step 8: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/playwright.config.ts frontend/e2e
git commit -m "chore(frontend): setup floating-ui + playwright screenshot harness; fix demoMode test env"
```

---

### Task 1 (#3): Handle de resize visível no dark

**Files:**
- Modify: `frontend/src/index.css` (ou o CSS global onde ficam overrides) — adicionar override do handle.
- Test: verificação visual (screenshot) — jsdom não estiliza.

**Interfaces:**
- Consumes: markup do RGL (`.react-grid-item > .react-resizable-handle`).
- Produces: handle visível; nenhuma mudança de API.

- [ ] **Step 1: Localizar o CSS global**

Run: `grep -rn "@import\|:root\|--color-line-strong" frontend/src/*.css | head`
Identificar o arquivo de estilos global (provável `src/index.css`).

- [ ] **Step 2: Adicionar override (só no editor)**

`DashboardGrid` já envolve o grid num `div.relative`. Adicionar uma classe
`editing` nesse wrapper quando `editing` (ver Task nota) e escrever:

```css
/* Handle de resize: SVG default é escuro e some no tema dark. Realçamos com
   a cor de linha do tema e aumentamos o grip + área de clique. */
.dashboard-grid-editing .react-resizable-handle::after {
  width: 8px;
  height: 8px;
  right: 4px;
  bottom: 4px;
  border-right: 2px solid var(--color-line-strong);
  border-bottom: 2px solid var(--color-line-strong);
}
.dashboard-grid-editing .react-resizable-handle:hover::after {
  border-color: var(--color-primary);
}
```

Em `DashboardGrid.tsx`, adicionar `dashboard-grid-editing` à className do wrapper
quando `editing`:

```tsx
<div ref={containerRef} className={`relative${editing ? ' dashboard-grid-editing' : ''}`}>
```

- [ ] **Step 3: Verificação visual**

Run: `ADMIN_PW=<senha> npm run shot`
Expected: no `editor-escuro.png`, o grip do canto inferior-direito dos cards está visível (linhas claras). Comparar com baseline.

- [ ] **Step 4: Suite + commit**

Run: `npx vitest run` (Expected: sem regressão; DashboardGrid ainda 5/5)

```bash
git add frontend/src/index.css frontend/src/components/DashboardGrid.tsx
git commit -m "fix(frontend): handle de resize visivel no tema dark (grip com cor de tema)"
```

---

### Task 2 (#1): Timeseries — título + WindowSelector

**Files:**
- Modify: `frontend/src/components/widgets/TimeseriesWidget.tsx`
- Test: `frontend/src/components/widgets/TimeseriesWidget.test.tsx` (criar)

**Interfaces:**
- Consumes: `WindowSelector({ value, onChange })` (existente), `useSensors()`,
  `useHistory(sensorCode, window)`, `useThreshold`, `useLiveTail`.
- Produces: `TimeseriesWidget` renderiza header (título + seletor) + chart; janela mutável.

- [ ] **Step 1: Teste falho — renderiza título e seletor, troca janela**

```tsx
// TimeseriesWidget.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TimeseriesWidget } from './TimeseriesWidget'

vi.mock('../../lib/queries', () => ({
  useSensors: () => ({ data: [{ sensor_code: 'S1', name: 'Sensor Um', area: { area_code: 'A', name: 'Área' } }] }),
  useHistory: vi.fn(() => ({ data: undefined })),
  useThreshold: () => ({ data: null }),
}))
vi.mock('../../lib/useLiveTail', () => ({ useLiveTail: () => ({ tail: [] }) }))
vi.mock('../TimeSeriesChart', () => ({ TimeSeriesChart: () => <div data-testid="chart" /> }))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('TimeseriesWidget', () => {
  it('mostra titulo do sensor e o seletor de janela', () => {
    wrap(<TimeseriesWidget sensorCode="S1" />)
    expect(screen.getByText('Sensor Um')).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Janela temporal' })).toBeInTheDocument()
  })

  it('troca a janela ao clicar num chip', async () => {
    const { useHistory } = await import('../../lib/queries')
    wrap(<TimeseriesWidget sensorCode="S1" defaultWindow="24h" />)
    await userEvent.click(screen.getByRole('button', { name: '7d' }))
    expect(useHistory).toHaveBeenLastCalledWith('S1', '7d')
  })
})
```

- [ ] **Step 2: Rodar (falha)**

Run: `npx vitest run src/components/widgets/TimeseriesWidget.test.tsx`
Expected: FAIL (sem título/seletor).

- [ ] **Step 3: Implementar header no widget**

```tsx
import { useState } from 'react'
import { useHistory, useThreshold, useSensors } from '../../lib/queries'
import { useLiveTail } from '../../lib/useLiveTail'
import { TimeSeriesChart } from '../TimeSeriesChart'
import { WindowSelector } from '../WindowSelector'
import { WidgetPlaceholder } from './WidgetPlaceholder'
import type { Window } from '../../lib/types'

export function TimeseriesWidget({ sensorCode, defaultWindow = '24h' }: {
  sensorCode: string
  defaultWindow?: Window
}) {
  const [window, setWindow] = useState<Window>(defaultWindow)
  const history = useHistory(sensorCode, window)
  const threshold = useThreshold(sensorCode)
  const { tail } = useLiveTail(sensorCode)
  const sensor = (useSensors().data ?? []).find((s) => s.sensor_code === sensorCode)

  if (!sensorCode) return <WidgetPlaceholder texto="Configurar sensor" />

  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex items-center gap-2">
        <span className="truncate text-sm font-bold" style={{ color: 'var(--color-ink)' }}>
          {sensor?.name ?? sensorCode}
        </span>
        <div className="ml-auto">
          <WindowSelector value={window} onChange={setWindow} />
        </div>
      </div>
      <div className="min-h-0 flex-1">
        <TimeSeriesChart history={history.data} threshold={threshold.data ?? null} tail={tail} />
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Rodar (passa)**

Run: `npx vitest run src/components/widgets/TimeseriesWidget.test.tsx`
Expected: PASS 2/2.

- [ ] **Step 5: Verificação visual + commit**

Run: `ADMIN_PW=<senha> npm run shot` (adicionar um timeseries via config p/ ver).
Expected: título + chips no topo do widget.

```bash
git add frontend/src/components/widgets/TimeseriesWidget.tsx frontend/src/components/widgets/TimeseriesWidget.test.tsx
git commit -m "feat(frontend): timeseries widget com titulo e seletor de janela"
```

---

### Task 3 (#2): Responsividade — container queries + fill

**Files:**
- Modify: `frontend/src/components/WidgetFrame.tsx` (root `@container` + h-full flex)
- Modify: `frontend/src/components/TimeSeriesChart.tsx` (altura fixa → fill)
- Modify: `frontend/src/components/widgets/KpiWidget.tsx` (fonte fluida)
- Test: ajustar `TimeSeriesChart.test.tsx` se checar height; `WidgetFrame` visual.

**Interfaces:**
- Consumes: markup dos widgets.
- Produces: widgets preenchem o frame; chart ocupa 100% da altura do card.

- [ ] **Step 1: WidgetFrame vira container + fill**

Modify `WidgetFrame.tsx` root:

```tsx
<div data-testid="widget-frame" className="@container relative flex h-full w-full flex-col overflow-hidden">
```

(o `descriptor.render(widget)` deve ficar num wrapper `flex-1 min-h-0` p/ o
conteúdo herdar altura:)

```tsx
<div className="min-h-0 flex-1">{descriptor.render(widget)}</div>
```

- [ ] **Step 2: TimeSeriesChart preenche a altura**

Modify `TimeSeriesChart.tsx` retorno:

```tsx
return <div ref={el} style={{ width: '100%', height: '100%', minHeight: 160 }} />
```

Verificar em `useECharts` se há `resize` observer; se não, garantir `chart.resize()`
ao mudar tamanho (o ResponsiveGridLayout dispara resize da window ao redimensionar,
mas resize do card não é window-resize — se o chart não acompanhar, adicionar
`ResizeObserver` no `useECharts` chamando `chart.resize()`).

- [ ] **Step 3: KpiWidget fonte fluida**

Modify `KpiWidget.tsx` o valor:

```tsx
<span className="font-bold tabular-nums text-[clamp(1.25rem,8cqw,2.25rem)]" style={{ color: cor }}>
```

(`cqw` = 1% da largura do container query; escala o número com o card.)

- [ ] **Step 4: Testes**

Run: `npx vitest run src/components/widgets src/components/TimeSeriesChart.test.tsx src/components/DashboardGrid.test.tsx`
Expected: PASS (ajustar assert de height em TimeSeriesChart.test se existir).

- [ ] **Step 5: Verificação visual + commit**

Run: `ADMIN_PW=<senha> npm run shot`
Expected: redimensionar um card (manual) → conteúdo se ajusta; chart preenche; KPI escala. Screenshot mostra widgets sem corte.

```bash
git add frontend/src/components/WidgetFrame.tsx frontend/src/components/TimeSeriesChart.tsx frontend/src/components/widgets/KpiWidget.tsx
git commit -m "feat(frontend): widgets responsivos ao card (container queries + fill)"
```

---

### Task 4 (#5): Popover de config ancorado (floating-ui)

**Files:**
- Modify: `frontend/src/components/WidgetFrame.tsx` (dono do popover ancorado ao ⚙)
- Modify: `frontend/src/components/DashboardGrid.tsx` (passar `onChange`/config down)
- Modify: `frontend/src/components/DashboardEditor.tsx` (remover popover do topo)
- Test: `frontend/src/components/WidgetFrame.test.tsx` (criar) + ajustar DashboardEditor.

**Interfaces:**
- Consumes: `@floating-ui/react` (`useFloating`, `offset`, `flip`, `shift`,
  `autoUpdate`, `FloatingPortal`), `WidgetConfigPopover`.
- Produces: `WidgetFrame` recebe `onChange?: (w: WidgetInstance) => void`;
  quando editando e o ⚙ é clicado, abre popover ancorado. `DashboardGrid`
  ganha prop `onWidgetChange?: (w) => void` repassada ao frame.

- [ ] **Step 1: Teste falho — popover abre ancorado ao clicar ⚙**

```tsx
// WidgetFrame.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { WidgetFrame } from './WidgetFrame'
import type { WidgetInstance } from '../lib/layout/schema'

vi.mock('../lib/queries', () => ({ useSensors: () => ({ data: [] }) }))

const w: WidgetInstance = { id: 'k1', type: 'kpi', layout: { x: 0, y: 0, w: 2, h: 2 }, binding: {}, options: {} }

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('WidgetFrame edição', () => {
  it('abre o popover de config ao clicar no botão configurar', async () => {
    wrap(<WidgetFrame widget={w} editing onChange={vi.fn()} onRemove={vi.fn()} />)
    expect(screen.queryByText('KPI (valor único)')).toBeNull()
    await userEvent.click(screen.getByLabelText('Configurar widget'))
    // WidgetConfigPopover mostra o label do tipo no header
    expect(screen.getByText('KPI (valor único)')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Rodar (falha)**

Run: `npx vitest run src/components/WidgetFrame.test.tsx`
Expected: FAIL.

- [ ] **Step 3: WidgetFrame vira dono do popover**

```tsx
import { useState } from 'react'
import { useFloating, offset, flip, shift, autoUpdate, FloatingPortal } from '@floating-ui/react'
import type { WidgetInstance } from '../lib/layout/schema'
import { WIDGET_REGISTRY } from '../lib/widgets/registry'
import { WidgetConfigPopover } from './WidgetConfigPopover'

export function WidgetFrame({ widget, editing, onChange, onRemove }: {
  widget: WidgetInstance
  editing: boolean
  onChange?: (w: WidgetInstance) => void
  onRemove?: () => void
}) {
  const descriptor = WIDGET_REGISTRY[widget.type]
  const [open, setOpen] = useState(false)
  const { refs, floatingStyles } = useFloating({
    open, onOpenChange: setOpen, placement: 'bottom-end',
    middleware: [offset(6), flip(), shift({ padding: 8 })], whileElementsMounted: autoUpdate,
  })

  return (
    <div data-testid="widget-frame" className="@container relative flex h-full w-full flex-col overflow-hidden">
      {editing && (
        <div className="absolute right-1 top-1 z-10 flex gap-1">
          <button ref={refs.setReference} type="button" onClick={() => setOpen((o) => !o)}
                  aria-label="Configurar widget" className="rounded bg-black/40 px-1.5 text-xs text-white">⚙</button>
          <button type="button" onClick={onRemove} aria-label="Remover widget"
                  className="rounded bg-black/40 px-1.5 text-xs text-white">✕</button>
        </div>
      )}
      <div className="min-h-0 flex-1">{descriptor.render(widget)}</div>
      {editing && open && onChange && (
        <FloatingPortal>
          <div ref={refs.setFloating} style={floatingStyles} className="z-50 w-60">
            <WidgetConfigPopover widget={widget} onChange={onChange} onClose={() => setOpen(false)} />
          </div>
        </FloatingPortal>
      )}
    </div>
  )
}
```

- [ ] **Step 4: DashboardGrid repassa onChange**

Modify `DashboardGrid.tsx`: adicionar prop `onWidgetChange?: (w: WidgetInstance) => void`
e no map trocar `onConfigure`/`onRemove` por:

```tsx
<WidgetFrame widget={w} editing={editing}
  onChange={onWidgetChange} onRemove={onRemove ? () => onRemove(w.id) : undefined} />
```

Remover a prop `onConfigure` do tipo e da assinatura (não é mais usada).
Importar `WidgetInstance` do schema.

- [ ] **Step 5: DashboardEditor remove popover do topo**

Modify `DashboardEditor.tsx`: apagar o bloco `{configuringWidget && (...)}` e o
state `configuring`; passar `onWidgetChange={updateWidget}` ao `DashboardGrid`:

```tsx
<DashboardGrid layout={draft} editing onLayoutChange={setDraft}
  onWidgetChange={updateWidget} onRemove={removeWidget} />
```

- [ ] **Step 6: Rodar testes**

Run: `npx vitest run src/components/WidgetFrame.test.tsx src/components/DashboardGrid.test.tsx`
Expected: PASS. Ajustar DashboardGrid.test se referenciava `onConfigure`.

- [ ] **Step 7: Verificação visual + commit**

Run: `ADMIN_PW=<senha> npm run shot` (rolar a página + abrir config de um card lá embaixo)
Expected: popover aparece colado ao ⚙ do widget, não no topo.

```bash
git add frontend/src/components/WidgetFrame.tsx frontend/src/components/WidgetFrame.test.tsx frontend/src/components/DashboardGrid.tsx frontend/src/components/DashboardEditor.tsx
git commit -m "feat(frontend): popover de config ancorado ao widget (floating-ui)"
```

---

### Task 5 (#4): Adicionar card por drag da paleta (RGL droppable)

**Files:**
- Modify: `frontend/src/components/WidgetPalette.tsx` (itens `draggable`)
- Modify: `frontend/src/components/DashboardEditor.tsx` (estado do tipo arrastado + onDrop)
- Modify: `frontend/src/components/DashboardGrid.tsx` (`isDroppable`/`onDrop`/`droppingItem`)
- Modify: `frontend/src/lib/widgets/newWidget.ts` (aceitar posição opcional)
- Test: `frontend/src/lib/widgets/newWidget.test.ts` (posição), `WidgetPalette` dnd.

**Interfaces:**
- Consumes: RGL `onDrop(layout, item, e)`, `droppingItem`, `isDroppable`.
- Produces: `newWidget(type, existing, pos?: {x:number;y:number})`; paleta emite
  `onDragStartType(type)` além de `onAdd`.

- [ ] **Step 1: newWidget aceita posição — teste falho**

Adicionar a `newWidget.test.ts`:

```ts
it('usa a posição informada quando fornecida', () => {
  const w = newWidget('kpi', [], { x: 4, y: 2 })
  expect(w.layout).toMatchObject({ x: 4, y: 2 })
})
```

Run: `npx vitest run src/lib/widgets/newWidget.test.ts` → FAIL.

- [ ] **Step 2: Implementar posição em newWidget**

```ts
export function newWidget(type: WidgetType, existing: WidgetInstance[], pos?: { x: number; y: number }): WidgetInstance {
  const desc = WIDGET_REGISTRY[type]
  const maxY = existing.reduce((m, w) => Math.max(m, w.layout.y + w.layout.h), 0)
  return {
    id: `${type}-${crypto.randomUUID().slice(0, 8)}`,
    type,
    layout: {
      x: pos?.x ?? 0,
      y: pos?.y ?? maxY,
      w: desc.defaultSize.w, h: desc.defaultSize.h,
      minW: desc.minSize.w, minH: desc.minSize.h,
    },
    binding: {},
    options: type === 'alarms' ? { scope: 'site' } : {},
  }
}
```

Run: `npx vitest run src/lib/widgets/newWidget.test.ts` → PASS.

- [ ] **Step 3: WidgetPalette — itens draggable**

Adicionar prop `onDragStartType?: (t: WidgetType) => void`. Nos botões da lista:

```tsx
<button key={t} type="button" draggable
  onDragStart={(e) => { e.dataTransfer.setData('text/widget-type', t); onDragStartType?.(t) }}
  onClick={() => handlePick(t)}
  className="rounded border px-2 py-1 text-left text-xs whitespace-nowrap cursor-grab"
  style={{ borderColor: 'var(--color-muted)' }}>
  + {WIDGET_REGISTRY[t].label}
</button>
```

(Mantém o clique como fallback: clica = adiciona no slot livre; arrasta = posiciona.)

- [ ] **Step 4: DashboardGrid — droppable**

Adicionar props `droppingType?: WidgetType | null` e `onDropWidget?: (pos: {x:number;y:number}) => void`.
No `ResponsiveGridLayout`:

```tsx
isDroppable={editing}
droppingItem={droppingType ? { i: '__dropping__', w: WIDGET_REGISTRY[droppingType].defaultSize.w, h: WIDGET_REGISTRY[droppingType].defaultSize.h } : undefined}
onDrop={(_layout, item) => { if (item) onDropWidget?.({ x: item.x, y: item.y }) }}
```

Importar `WIDGET_REGISTRY`. Nota: `onDrop` do RGL exige que o elemento arrastado
tenha o atributo — RGL escuta `onDragOver`/`onDrop` no container quando
`isDroppable`; o `dataTransfer` da paleta satisfaz o drag HTML5.

- [ ] **Step 5: DashboardEditor — fio do estado**

```tsx
const [droppingType, setDroppingType] = useState<WidgetType | null>(null)
// ...
<WidgetPalette onAdd={addWidget} onDragStartType={setDroppingType} />
// ...
<DashboardGrid layout={draft} editing onLayoutChange={setDraft}
  onWidgetChange={updateWidget} onRemove={removeWidget}
  droppingType={droppingType}
  onDropWidget={(pos) => { if (droppingType) { setDraft((d) => ({ ...d, widgets: [...d.widgets, newWidget(droppingType, d.widgets, pos)] })); setDroppingType(null) } }} />
```

- [ ] **Step 6: Teste — paleta seta tipo no dragstart**

`WidgetPalette.test.tsx` (criar ou ampliar):

```tsx
it('emite o tipo ao iniciar o arraste', () => {
  const onDragStartType = vi.fn()
  render(<WidgetPalette onAdd={vi.fn()} onDragStartType={onDragStartType} />)
  fireEvent.click(screen.getByRole('button', { name: '+ Adicionar' }))
  const item = screen.getByText(/Card de área/)
  fireEvent.dragStart(item, { dataTransfer: { setData: vi.fn() } })
  expect(onDragStartType).toHaveBeenCalledWith('area')
})
```

Run: `npx vitest run src/components/WidgetPalette.test.tsx` → PASS.

- [ ] **Step 7: Verificação visual (crítica p/ #4)**

Playwright dnd real:

```ts
// e2e/drag-add.spec.ts
import { test, expect } from '@playwright/test'
import { loginAndEnterEdit } from './helpers'

test('arrasta um widget da paleta pra grade', async ({ page }) => {
  await loginAndEnterEdit(page)
  await page.getByRole('button', { name: '+ Adicionar' }).click()
  const source = page.getByText('KPI (valor único)')
  const grid = page.locator('.react-grid-layout')
  const before = await page.getByTestId('widget-frame').count()
  await source.dragTo(grid, { targetPosition: { x: 300, y: 200 } })
  await expect(page.getByTestId('widget-frame')).toHaveCount(before + 1)
  await page.screenshot({ path: 'e2e/__shots__/drag-add.png' })
})
```

Run: `ADMIN_PW=<senha> npx playwright test e2e/drag-add.spec.ts`
Expected: contagem de widgets +1; card posicionado onde soltou.

- [ ] **Step 8: Suite completa + commit**

Run: `npx vitest run` (Expected: tudo verde)

```bash
git add frontend/src/components/WidgetPalette.tsx frontend/src/components/DashboardGrid.tsx frontend/src/components/DashboardEditor.tsx frontend/src/lib/widgets/newWidget.ts frontend/src/lib/widgets/newWidget.test.ts frontend/src/components/WidgetPalette.test.tsx frontend/e2e/drag-add.spec.ts
git commit -m "feat(frontend): adicionar widget por drag-and-drop da paleta (RGL droppable)"
```

---

## Self-Review (feito)

- **Cobertura do spec:** #1→Task2, #2→Task3, #3→Task1, #4→Task5, #5→Task4;
  setup/deps/demoMode/screenshots→Task0. Sem lacunas.
- **Placeholders:** nenhum "TBD"; código concreto em cada step. Onde o
  implementador precisa casar seletores reais (LoginPage, ThemeToggle), está
  explícito o que casar.
- **Consistência de tipos:** `newWidget(type, existing, pos?)` usado igual em
  Task5; `onWidgetChange`/`onChange` coerentes entre DashboardGrid↔WidgetFrame
  (Task4) e reusado em Task5. `droppingType`/`onDropWidget` definidos em Task5.
- **Risco conhecido:** RGL `onDrop` + drag HTML5 da paleta — se o RGL não captar
  o drop externo, fallback é o clique (já mantido) + investigar `isDroppable`
  exige `onDragOver` no container (RGL cuida quando `isDroppable`). Task5 Step7
  (Playwright) é o gate real.
