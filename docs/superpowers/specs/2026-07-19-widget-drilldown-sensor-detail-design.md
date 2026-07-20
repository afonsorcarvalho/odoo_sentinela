# Design: Drill-down de widget → Detalhe do sensor (D3)

## Contexto

`frontend/src/components/SensorDetailPanel.tsx` existe, tem teste
(`SensorDetailPanel.test.tsx`) e está **desconectado**: foi removido do fluxo
principal na Task 14 (ver `App.test.tsx:39` — "SensorDetailPanel foi removido do
fluxo principal") e hoje não é montado em lugar nenhum. É código morto de alto
valor: já compõe `LiveReadout` (valor + estado + trilho de tolerância),
`WindowSelector` e `TimeSeriesChart`.

Objetivo do D3 (backlog tema D): **religar** esse painel via drill-down. No
dashboard de widgets, clicar no sensor ativo de um `AreaCard` (widget de área)
abre o Detalhe do sensor — gráfico histórico, tolerâncias, cauda ao vivo — **sem
sair do dashboard**.

A oportunidade já está meio pronta: `AreaCard` dispara
`onSelectSensor(sensor_code)` ao clicar no valor (linha 86). Hoje o
`AreaWidget` engole essa callback com `onSelectSensor={() => {}}`
(`AreaWidget.tsx:29`) porque o widget é read-only. O D3 é ligar essa callback a
um painel de detalhe.

## Decisão de abordagem

### Transporte da callback: **React context**, não prop-threading

O caminho de render é `DashboardPage → DashboardGrid → WidgetFrame →
WIDGET_REGISTRY[type].render(widget) → AreaWidget`. A assinatura do registry é
`render: (widget: WidgetInstance) => ReactNode` (`registry.tsx:16`) — **só recebe
o widget**, sem slot para callbacks. Threading de prop exigiria mudar a
assinatura de `WidgetDescriptor.render`, de `DashboardGrid`, de `WidgetFrame` e
de todos os widgets — invasivo e sem relação com o D3.

**Escolha:** um `DrillDownContext` provido pela `DashboardPage` (só no ramo de
view). `AreaWidget` consome via `useContext` e passa o valor a
`onSelectSensor`. Nada nas assinaturas de `DashboardGrid`/`WidgetFrame`/registry
muda. É o padrão que a indireção do registry pede.

```ts
// lib/drilldown/DrillDownContext.ts
type DrillDown = { open: (sensorCode: string) => void }
const DrillDownContext = createContext<DrillDown | null>(null)
// AreaWidget: const drill = useContext(DrillDownContext)
//             onSelectSensor={drill ? drill.open : () => {}}
```

Sem provider (ex.: modo edição, testes isolados do widget), `AreaWidget` cai no
no-op atual — comportamento inalterado, sem regressão.

### Apresentação: **overlay (drawer lateral direito)**, não rota nem modal-central

- **Rota** está descartada: não há router no fluxo (a `DashboardPage` renderiza
  direto; o painel foi removido do fluxo na Task 14). Introduzir roteamento é
  fora do fase-1 enxuto e contraria "sem sair do dashboard".
- **Drawer lateral** (desliza da direita, ~`min(560px, 100vw)`, backdrop
  escurecendo o dashboard atrás) vence sobre modal central porque: (a) mantém o
  contexto do dashboard visível ao lado — o operador vê a área de onde veio; (b)
  dá **altura definida** naturalmente (`h-screen`), que é o que o gráfico precisa
  (ver DT/M2 abaixo); (c) é o padrão de "detalhe sem perder a lista".

Um modal central também serviria **se** garantir altura definida + scroll
interno; o drawer é preferido por (a)/(b). A decisão de layout do drawer é o que
resolve o bug de altura — ver seção DT/M2.

## O que dispara o drill-down

- **Gatilho:** clicar no botão de valor do sensor ativo do `AreaCard`
  (`AreaCard.tsx:84-103`) — já chama `onSelectSensor(activeSensor.sensor_code)`.
  **Reaproveita a callback existente, sem mudar a API do `AreaCard`.**
- Os **dots** do carrossel continuam com sua função atual (trocar o sensor
  visível no card); não abrem drill-down.
- Fase-1: só o **widget de área** (`AreaWidget`) dispara. KPI e Timeseries ficam
  fora (ver "Fora de escopo").

## Como o painel recebe o sensor selecionado

`SensorDetailPanel` é **puramente apresentacional** — recebe
`value/state/threshold/history/tail/group/window` e **não busca nada**. Logo o
drill-down precisa de um **novo container** que fecha os hooks, no mesmo padrão
do `TimeseriesWidget` (`TimeseriesWidget.tsx`), acrescido dos campos de leitura:

```
SensorDetailDrawer (novo — container + overlay)
  estado local: window (useState<Window>, default '24h')
  wiring de hooks a partir do sensorCode selecionado:
    sensors   = useSensors().data
    group     = groupSensorsByArea(sensors).find(g contém sensorCode)
    unidade   = sensor.unidade
    threshold = useThreshold(sensorCode).data ?? null
    history   = useHistory(sensorCode, window).data
    { last, tail } = useLiveTail(sensorCode)
    value     = last?.value ?? null
    state     = last?.alarm_state
  →  <SensorDetailPanel
        group group  selectedCode={sensorCode}
        onSelectSensor={setSensorCode}   // troca de métrica DENTRO do painel
        threshold unidade value state
        window onWindowChange={setWindow}
        history tail />
```

### Estado e a callback de duplo uso

- `selectedSensorCode: string | null` mora na `DashboardPage` (`useState`).
  `null` = drawer fechado; string = aberto naquele sensor.
- A **mesma** `onSelectSensor` serve a dois papéis, e é isso que torna o reuso
  elegante:
  1. disparada pelo `AreaCard` (via context) → **abre** o drawer;
  2. disparada pelos botões de métrica **dentro** do `SensorDetailPanel`
     (`SensorDetailPanel.tsx:42-57`) → **troca o sensor** exibido sem fechar o
     drawer (só troca `selectedSensorCode` → re-fecha os hooks do container).
- O `group` do container é derivado do próprio `sensorCode` (acha o grupo que o
  contém), então trocar de métrica entre sensores da mesma área continua no
  mesmo grupo.

## Modo edição vs view

Drill-down funciona **só em view**. A `DashboardPage` já ramifica
`{editing ? <DashboardEditor/> : <DashboardGrid/>}` (`DashboardPage.tsx:81-85`):

- O `DrillDownContext.Provider` embrulha **apenas o ramo de view**
  (`<DashboardGrid editing={false}>`). No ramo de edição não há provider, então
  `AreaWidget` cai no no-op — sem gate extra, sem risco.
- Detalhe que reforça a necessidade do gate: `DashboardGrid` usa
  `draggableCancel="button"` (`DashboardGrid.tsx`), ou seja botões **não**
  iniciam drag. Sem o isolamento por ramo, clicar no valor do card em modo
  edição dispararia drill-down em vez de deixar o admin manipular o widget. O
  `DashboardEditor` renderiza a mesma `DashboardGrid` com widgets vivos — o
  isolamento "provider só no ramo de view" é o que garante o comportamento
  correto independentemente disso.

## DT/M2 — altura do container (tratar explicitamente)

**O bug.** `TimeSeriesChart` (`TimeSeriesChart.tsx:29`) renderiza
`<div style={{ width:'100%', height:'100%', minHeight:160 }}>`. `height:100%` só
resolve para um valor real se **algum ancestral tiver altura definida**; senão
resolve para `auto` e o gráfico trava em `minHeight:160` (baixo e fixo). É a
dívida M2 do backlog: afeta exatamente o `SensorDetailPanel`, hoje latente
porque o painel não está montado. Ao religar no drill-down, o bug deixa de ser
latente — **a spec precisa resolver, e são duas partes que devem valer juntas:**

1. **O overlay dá altura definida.** O drawer é `h-screen` (ou modal com altura
   explícita + scroll interno). Sem isso, nenhum ancestral do chart tem altura →
   colapso em 160.

2. **O `SensorDetailPanel` precisa virar coluna flex e embrulhar o chart.** Hoje
   ele renderiza `<TimeSeriesChart .../>` como filho nu (`SensorDetailPanel.tsx:78`),
   sem wrapper de altura. A correção espelha o padrão **já provado no repo** pelo
   `TimeseriesWidget` (`TimeseriesWidget.tsx:30-45`):
   - o painel passa a `flex h-full flex-col` (herdando a altura do drawer);
   - o cabeçalho/readout/tolerância/seletor ficam em altura natural;
   - o chart é embrulhado em `<div className="min-h-0 flex-1"><TimeSeriesChart/></div>`,
     para crescer e preencher o espaço restante em vez de colapsar.
   (`WidgetFrame.tsx:39` já usa `min-h-0 flex-1` pelo mesmo motivo — é o padrão da casa.)

3. **Verificação é no browser (Playwright), não em jsdom.** Os testes mockam
   `echarts` (`SensorDetailPanel.test.tsx:5`), então um teste unitário **nunca**
   pega o colapso de 160px — o canvas não existe em jsdom. A altura correta do
   gráfico dentro do drawer é validada **visualmente no browser** (Playwright;
   chrome-devtools-mcp não sobe no WSL2). A spec não deve fingir que um teste
   unitário cobre isso.

## Fechar / voltar

- **Fechar:** botão ✕ no cabeçalho do drawer, tecla **Esc**, e clique no
  **backdrop** — os três setam `selectedSensorCode = null`.
- **A11y** (a spec original enfatiza uso com luvas / teclado / contraste, ver
  `2026-07-18-frontend-sensor-detail-design.md` §3): o drawer é `role="dialog"`
  `aria-modal="true"`, com **focus trap** enquanto aberto e **restauração de
  foco** ao botão de origem (o valor do `AreaCard`) ao fechar. Já há
  `@floating-ui/react` no projeto (`WidgetFrame.tsx`) — `FloatingFocusManager` +
  `useDismiss` cobrem trap/Esc/backdrop sem dependência nova.

## Escopo — fase 1 (enxuto)

- `DrillDownContext` + provider no ramo de view da `DashboardPage`.
- `AreaWidget` consome o context e liga `onSelectSensor` (substitui o no-op).
- `selectedSensorCode` na `DashboardPage`.
- Novo `SensorDetailDrawer` (overlay + container de hooks) montando o
  `SensorDetailPanel` existente.
- Ajuste de altura no `SensorDetailPanel` (flex-col + wrapper `min-h-0 flex-1`
  no chart) — DT/M2.
- Fechar por ✕/Esc/backdrop, com focus trap e restauração de foco.

## Fora de escopo (fase 1)

- Drill-down a partir dos widgets **KPI** e **Timeseries** (só área nesta fase).
- **Deep-link / estado na URL** do sensor aberto (exigiria router — descartado).
- Múltiplos painéis de detalhe simultâneos.
- **Ack/resolver alarme** e **indicador de sensor offline / dado velho** —
  pertencem ao backlog tema A (confiabilidade), **não** ao D3; nomeados aqui só
  para o reviewer não os esperar.
- Persistir a janela (`window`) escolhida por sensor entre aberturas.

## Testes a cobrir

Unitários (Vitest + Testing Library; `echarts` mockado):

- Clicar no valor de um `AreaCard` dentro do provider chama `open(sensorCode)` e
  abre o drawer com o sensor certo (título "Área · Métrica", valor).
- Sem provider (widget isolado / modo edição), clicar no valor **não** abre nada
  (no-op) — garante o gate por ramo.
- Botão de métrica dentro do painel troca `selectedSensorCode` **sem fechar** o
  drawer (re-render com o outro sensor da mesma área).
- Trocar `window` no `WindowSelector` dispara `useHistory(code, window)` com a
  nova janela (mesma prova de "refetch histórico" da spec original).
- Fechar por ✕, Esc e backdrop seta `selectedSensorCode = null` (drawer some).
- Foco: ao abrir vai pro drawer; ao fechar volta ao botão de origem.

Browser (Playwright — **obrigatório** para DT/M2, jsdom não cobre):

- Com o drawer aberto, o `TimeSeriesChart` **preenche a altura** disponível (não
  fica travado em 160px). Verificação visual/medida da altura renderizada do
  canvas.
