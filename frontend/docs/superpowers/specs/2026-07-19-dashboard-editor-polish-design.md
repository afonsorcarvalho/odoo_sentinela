# Dashboard Editor — Polish de UX (5 itens)

Data: 2026-07-19
Status: aprovado, pronto p/ plano

## Contexto

O editor de dashboard customizável (grid react-grid-layout, admin-only) já
funciona: drag/resize voltaram após o fix de `process.env.DRAGGABLE_DEBUG`
(Vite não polyfilla `process`), e a grade de fundo do modo edição (overlay de
linhas alinhado ao passo do RGL) já está no ar. Este spec cobre 5 refinamentos
de usabilidade levantados na verificação visual. **UX em primeiro lugar.**

Stack relevante: React 19.2, Vite 8, Tailwind v4.3 (@container nativo),
react-grid-layout 1.5.3 (isDroppable/onDrop/droppingItem disponíveis),
`WindowSelector` já existe e é reutilizável.

## Itens

### #1 — Timeseries: controles de janela + título

**Problema:** `TimeseriesWidget` fixa a janela (`useState` sem setter exposto) e
não renderiza título nem os controles hora/dia/semana/30d.

**Design:**
- Header compacto no topo do widget: título à esquerda (nome do sensor,
  resolvido via `useSensors` lookup pelo `sensorCode`; fallback = `sensorCode`),
  `WindowSelector` à direita.
- `window` vira state ativo; o setter liga no `onChange` do `WindowSelector`.
  Trocar a janela dispara `useHistory(sensorCode, window)` p/ a nova faixa.
- Sem novo componente de seletor — reusa `WindowSelector`.

**Interface:** `TimeseriesWidget` continua recebendo `{ sensorCode, defaultWindow }`.
Estado interno passa a ser mutável.

### #2 — Responsividade (container queries + fill)

**Problema:** conteúdo não se ajusta ao card. `TimeSeriesChart` tem `height: 320`
fixo; `KpiWidget` usa `text-3xl` fixo; `WidgetFrame` corta com `overflow-hidden`.

**Design (Tailwind v4 @container):**
- `WidgetFrame` root: `@container` + `h-full w-full flex flex-col`; conteúdo
  ocupa o frame em vez de transbordar.
- `TimeSeriesChart`: `height: 320` → preencher a altura do container
  (`flex-1`/`h-full`); ECharts redimensiona junto (o `useECharts` já observa
  resize — confirmar).
- `KpiWidget`: valor `text-3xl` → `clamp()` ou variantes `@container` (`@sm:`,
  `@md:`) p/ escalar com o card.
- Cada widget passa a assumir `h-full` e distribuir conteúdo; scroll interno
  só onde inevitável (ex.: lista de alarmes longa).

### #3 — Handle de resize visível no dark

**Problema:** o grip do react-resizable é um SVG escuro, quase invisível no
tema escuro.

**Design:** CSS scoped ao modo edição. Sobrescrever
`.react-resizable-handle::after` com `border-color: var(--color-line-strong)`,
aumentar o grip e a área de clique, realce no `:hover`. Aplicar só quando
editando (classe no container do grid ou seletor sob `.layout` em edição).

### #4 — Adicionar card por drag da paleta (RGL nativo)

**Problema:** `+Adicionar` coloca no próximo slot livre; usuário quer arrastar
e soltar na posição.

**Design (react-grid-layout droppable):**
- `DashboardGrid`: `isDroppable={editing}`, `onDrop(layout, item, e)`,
  `droppingItem={{ i: '__dropping__', w, h }}` com w/h do tipo arrastado.
- Itens da `WidgetPalette` viram `draggable`; `onDragStart` grava o tipo no
  `dataTransfer` (e num ref/estado no editor p/ definir o `droppingItem`).
- `onDrop` fornece x/y da célula → cria `newWidget(type)` naquela posição
  (adaptar `newWidget` p/ aceitar posição opcional, ou setar x/y no retorno).
- Cancelamento: soltar fora da grade ou Esc durante o drag HTML5 cancela
  nativamente (sem card criado).

**Nota UX:** o comportamento pedido originalmente ("fantasma segue o ponteiro,
clica pra fixar, Esc cancela") foi trocado por drag-and-drop nativo do RGL
(decisão do usuário) — mesma finalidade, menos código custom, com o
`droppingItem` do RGL servindo de fantasma durante o arraste.

### #5 — Popover de configurar ancorado (floating-ui)

**Problema:** `WidgetConfigPopover` é renderizado no topo do `DashboardEditor`;
com a página rolada, aparece longe do widget (quebra usabilidade).

**Design:**
- Nova dep: `@floating-ui/react`.
- `WidgetFrame` (modo edição) vira dono do popover: o botão ⚙ é a referência,
  `WidgetConfigPopover` flutua ancorado com `flip` + `shift` (auto-reposiciona).
- Remover o bloco de popover do topo do `DashboardEditor`; passar
  `widget`/`onChange`/`configuring` pra baixo (DashboardGrid → WidgetFrame) p/
  cada frame renderizar seu próprio popover ancorado.
- Fechar: clique fora / Esc / botão Fechar.

## Ordem de implementação

`#3 (CSS trivial)` → `#1 (título+seletor)` → `#2 (responsivo)` →
`#5 (floating-ui)` → `#4 (drag droppable, maior risco)`.

Cada item é uma task isolada (subagent-driven), com checkpoint de teste verde
entre elas.

## Estratégia de testes / verificação

- **Unit (vitest+jsdom):** por item — presença/ausência de controles, wiring de
  callbacks (ex.: `WindowSelector.onChange` → refetch; `onDrop` → novo widget na
  posição; popover ancorado renderiza junto ao botão). jsdom não calcula layout
  real, então geometria fina não é testável aqui.
- **Verificação visual (Playwright):** chrome-devtools MCP não sobe no WSL2 —
  usar Playwright p/ screenshots reais do modo edição (light + dark) validando
  UX/design/layout: título+seletor no chart, widgets preenchendo o card, handle
  de resize visível no dark, drag da paleta, popover ancorado ao ⚙. Screenshots
  são o critério de aceite de "usabilidade/design/layout".
- Suite completa verde ao fim de cada task (baseline atual: 213/214; a 1 falha
  `demoMode` é pré-existente, `.env.local` com `VITE_DEMO_MODE=true` carregado
  pelo vitest — corrigir de passagem com `env: { VITE_DEMO_MODE: '' }` no bloco
  test do vite.config).

## Deps novas

- `@floating-ui/react` (popover #5)
- `@playwright/test` (verificação visual) — dev only
