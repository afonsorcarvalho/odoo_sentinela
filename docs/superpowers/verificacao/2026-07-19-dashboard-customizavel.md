# Verificação — Dashboard Customizável por Site

**Data:** 2026-07-19
**Branch:** `feat/dashboard-customizavel`
**Plano:** [docs/superpowers/plans/2026-07-19-dashboard-customizavel.md](../plans/2026-07-19-dashboard-customizavel.md)

## Como foi verificado

- **Browser real** (não jsdom): Playwright headless com o Chromium em cache
  (`~/.cache/ms-playwright/chromium-1228`), dirigindo o dev server em **modo mock**.
  - `chrome-devtools-mcp` (agent-web) NÃO sobe neste WSL2 (erro "Target closed"); Playwright
    headless com `executablePath` explícito + `--no-sandbox` funcionou.
  - Modo mock via `.env.mock.local` (precedência Vite > `.env.local`, que estava em `real`),
    dev server `--mode mock --port 5188`. Admin simulado injetando um JWT com `is_admin:true`
    em `localStorage[sentinela_token]` via `addInitScript`.
- Script: `scratchpad/verify.mjs` (efêmero). Screenshots por marco.

## Marcos verificados (todos ✅)

| # | Marco | Resultado |
|---|---|---|
| 1 | Dashboard carrega com `defaultLayout` | 3 cards de área (Expurgo 20.3°C, Preparo 22.5°C, Arsenal 24.5°C) + painel Alarmes com eventos reais. Render real, não vazio. |
| 2 | Botão "Editar" visível (admin) | Presente. (Gate por `isAdmin` — some para não-admin, coberto por teste unitário.) |
| 3 | Modo edição | "+ Adicionar", "Salvar", "Cancelar"; cada widget ganha ⚙/✕. 4 widgets no default. |
| 4 | Adicionar KPI via paleta | 4 → 5 widgets. Novo KPI aparece no grid. |
| 4b | Configurar binding (popover) | Dropdown "Sensor" com 6 opções; selecionado `TEMP-EXP-01` (label "Temperatura — Expurgo"). |
| 5 | Salvar → volta a leitura | "Editar" reaparece (edição saiu). |
| 5b | **Round-trip via API mock** | Re-entrar em edição mostra **5 widgets** — o KPI salvo persistiu através de `saveLayout` → `getConfig`. |
| 6 | Colapso mobile (375px) | 1 coluna, widgets empilhados na ordem (Expurgo, Preparo, Arsenal, Alarmes com badge). |

- **0 erros de console / pageerror** durante todo o fluxo.
- **react-grid-layout + React 19** renderiza no browser real (chrome de edição, colapso
  responsivo). Fixado em `^1.5.3` (v2 removeu `WidthProvider`).

### Screenshots
`scratchpad/shot-1-default.png`, `shot-3-edit-mode.png`, `shot-4-after-add-kpi.png`,
`shot-4b-config-popover.png`, `shot-5-after-save.png`, `shot-5b-reedit-roundtrip.png`,
`shot-6-mobile.png`.

## Suítes finais

- **Backend:** `python3 -m pytest api/tests` → **55 passed** (Odoo + API vivos).
- **Frontend build:** `npm run build` → **✓ built** (após corrigir erro pré-existente de tipo
  em `chartOption.ts`, TS2322 markArea/echarts 6, que quebrava o build e o vitest escondia).
- **Frontend vitest:** `npx vitest run` → **212 passed, 1 failed**.
  - O 1 que falha é `src/lib/demoMode.test.ts` (`isDemoMode()` falso quando `VITE_DEMO_MODE`
    indefinido). Causa: o `.env.local` do ambiente de dev define `VITE_DEMO_MODE=true`, então
    `isDemoMode()` retorna `true`. **Pré-existente, dirigido por env, em código não tocado por
    esta feature** — passa em checkout limpo / CI sem esse `.env.local`.

## Observações não-bloqueantes (para polish futuro)

- **KpiWidget** renderiza o valor cru (sem `.toFixed(1)`), divergente do `AreaCard`. Cosmético.
- Ao **entrar em edição**, os valores live mostram "—" por um instante (live re-subscreve no
  remount) e repovoam. Cosmético.
- `id-collision` no `newWidget` foi endurecido para `crypto.randomUUID()` durante o review.
- Layout deixa área vazia abaixo dos cards no default (grid `rowHeight` fixo) — decisão de
  design, ajustável.
