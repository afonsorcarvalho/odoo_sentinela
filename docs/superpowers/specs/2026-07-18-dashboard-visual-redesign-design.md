# Design — Redesign visual do Dashboard Sentinela CME (AFR Design System)

> Spec de implementação. Substitui o sistema visual atual (`DESIGN.md`) e
> funde as rotas `/` (Overview) + `/sensor/:code` (Detalhe do Sensor) numa
> única tela de dashboard, seguindo fielmente o handoff de design em
> `docs/superpowers/Dashboard Sentinela CME/design_handoff_dashboard_sentinela_cme/`.

## 1. Objetivo e escopo

Recriar o dashboard usando o **AFR Design System** (handoff): tema
`control`/`document`, marca cyan, tipografia Inter+JetBrains Mono, cards com
borda esquerda colorida por status, topbar com identidade/relógio/selo de
integridade, painel de alarmes lateral e toasts. A estrutura de interação e
os dados (sensores, thresholds, histórico) continuam os mesmos do app atual
— isto é um refino visual + fusão de telas, não uma reescrita de domínio.

**Fora de escopo**: multi-site/multi-hospital (app é single-tenant por login
hoje — `/area/:areaCode` já documentou isso como fora de escopo, mantém-se);
layout de planta física da área; alteração do modelo de dados Odoo.

## 2. Rotas — fusão em `/`

Hoje: `/` (Overview, cards por área) → clica card → `/area/:areaCode`
(lista de sensores da área) → clica sensor → `/sensor/:code` (detalhe).

Depois: **`/` vira a tela única**, fiel ao handoff — todas as áreas como
cards (cada card com seus sensores), painel de detalhe do sensor
selecionado, painel de alarmes, tudo na mesma tela, sem navegar.

- `/area/:areaCode` e `/sensor/:code` deixam de ser rotas de navegação
  primária. Viram **deep-links**: ao abrir `/sensor/:code` diretamente,
  redireciona para `/?sensor=:code` e a tela já nasce com aquele sensor
  selecionado (útil para favoritos/links compartilhados). Mesma ideia para
  `/area/:areaCode` → `/?area=:areaCode` (seleciona a primeira área/sensor
  dela).
- `/login` inalterado (`AuthGuard` continua protegendo `/`).
- Seleção de área/sensor vira estado da própria `OverviewPage` (ou página
  renomeada — ver §4), refletido na querystring (não em rota), para permitir
  voltar/compartilhar sem recarregar dado.

## 3. Sistema visual — substitui `DESIGN.md`

O `DESIGN.md` atual (paleta OKLCH quase monocromática, Geist Mono,
`rounded-2xl`, sem cor de marca) é **substituído** pelos tokens do handoff.
Resumo (ver `colors_and_type.css` para a folha completa):

- **Tema**: `theme-control` (escuro, default — ambiente de monitoramento
  contínuo) / `theme-document` (claro — telas de gestão/relatório). Nomes
  semânticos, não `dark`/`light`.
- **Marca**: `--afr-cyan` (`#00b3c7` escuro / `#008a9b` claro) — única cor de
  ação/seleção, não decorativa.
- **Status** (IEC 60073/ISA-101, mantém a regra já validada no projeto):
  `--state-run` (verde), `--state-warn` (âmbar), `--state-alarm` (vermelho),
  sempre cor+ícone+texto, nunca só cor. Cada um com par `-soft` (fundo de
  chip/badge).
- **Tipografia**: Inter (UI) + JetBrains Mono (todo valor numérico —
  leitura, relógio, thresholds — sempre `tabular-nums`). Mantém a regra
  "Numeric-Is-Mono" já em vigor, só troca a família.
- **Raios**: `r-sm` 4px (chips), `r-md` 6px (cards/painéis/botões — menor
  que o `rounded-2xl` atual, visual mais "instrumento de controle" que
  "app consumer"), `r-pill` (pills/badges).
- **Elevação**: plano por padrão (mantém a regra "Flat-By-Default" atual);
  `--shadow-menu` só em tooltip do gráfico e toasts.
- **Espaçamento**: grid de 4px (`--s-1`…`--s-20`).

**Migração técnica**: projeto já usa Tailwind v4 CSS-first (`@theme` em
`frontend/src/index.css`, sem `tailwind.config.js`). Substituir o bloco
`@theme`/`.dark` atual pelos tokens AFR (nomes `--bg`/`--fg`/`--afr-cyan`/
`--state-*`, não os nomes antigos `--color-*`); trocar a classe de tema de
`.dark` para `theme-control`/`theme-document` no elemento raiz — `ThemeToggle`
muda a classe, não o mecanismo.

**Regra herdada, reaplicar aos tokens novos**: `color-mix` envolvendo
tinta/status **exige** `oklch(L 0 none)` ou equivalente sem matiz explícito
— bug real já resolvido no projeto (`crit`→roxo, `warn`→verde por
interpolação de matiz, ver memória `echarts-appendData-line`). Qualquer
`color-mix` novo introduzido pelos componentes do handoff (ex.: halo do
pulso "AO VIVO" em `color-mix(... 55%, transparent)`) precisa ser auditado
com essa regra antes de assumir que está certo visualmente.

## 4. Componentes

### Novos
- **Topbar** (sticky, `top:0`): marca "Sentinela CME", pill da unidade
  (nome vem do login/company Odoo — ver §5), selo "Registro íntegro",
  relógio ao vivo (mono, `HH:MM:SS`), indicador "AO VIVO" (pulso), toggle
  de tema.
- **AlarmPanel** + **AlarmItem**: coluna lateral sticky, lista de eventos
  (mais recente primeiro), contador, estado vazio.
- **ToastContainer** + **Toast**: disparado por novo alarme/normalização,
  auto-dispensa 6s.
- **DemoBanner** + botões de simulação: **atrás de feature flag**
  (`VITE_DEMO_MODE=true`, análogo ao `VITE_API_MODE` existente) — fora do
  flag, não renderiza nada; código fica no repo mas não aparece em produção
  por padrão.

### Restyle (mesma lógica, novo visual)
- `AreaCard` — ganha borda esquerda 3px de status, badge "!" de não
  conformidade do dia, chip de status com ícone.
- `LiveReadout`, `ToleranceRail`, `WindowSelector`, `TimeSeriesChart`,
  `ThemeToggle` — mesma função, tokens/raios/fontes novos. `TimeSeriesChart`
  ganha a faixa verde de conformidade + linhas de limite tracejadas do
  handoff (hoje a `ToleranceRail` já comunica faixa fora do gráfico; avaliar
  na implementação se os dois ficam redundantes ou se a rail vira só o chip
  compacto do card e o gráfico assume a faixa visual completa).

### Página
`OverviewPage` absorve o que hoje é `SensorDetailPage` (chart+readout) e
`AreaPage` (lista de sensores por área) — vira a tela única. `AreaPage` e
`SensorDetailPage` como arquivos somem; a lógica de seleção/agrupamento
(`groupSensorsByArea`, `useSensors`, `useThresholds`, `useLiveStatuses`)
é reaproveitada, não reescrita.

## 5. Dados — API real (não mock)

Estado real hoje (checado na master antes de escrever esta spec):
`authApi` real (`realAuthApi`, JWT); `metaApi`/`historyApi` têm endpoint
backend pronto (`/sensores`, `/sensores/{code}`, `/sensores/{code}/threshold`,
`/sensores/{code}/historico?window=1h|24h|7d|30d`) mas o frontend ainda usa
adapter mock para os três (`index.ts` força mock nesses); `liveApi` e
alarmes não têm endpoint algum ainda (ingestão grava, não expõe leitura).

Esta spec assume **tudo real** — os gaps abaixo viram tasks do plano de
implementação, não ficam mock:

| Peça | Estado | Trabalho necessário |
|---|---|---|
| `authApi` | ✅ real | nenhum |
| `metaApi` | endpoint pronto | escrever `real/metaApi.ts` (mesmo padrão de `real/authApi.ts`) |
| `historyApi` (janelas 1h/24h/7d/30d) | endpoint pronto | escrever `real/historyApi.ts` |
| `liveApi` ("Ao vivo", 60 pontos/1s do handoff) | sem endpoint dedicado | **decisão de design**: sem infra de streaming (SSE/WS) no projeto ainda — implementar como polling client-side do `historico?window=1h` (raw), reamostrando/mantendo janela dos últimos 60s no cliente, em vez de push real. Reavaliar para SSE só se o polling se mostrar insuficiente. |
| Alarmes (lista + contador) | sem endpoint de leitura | novo endpoint backend `GET /alarmes` (ativos + histórico recente), mesmo padrão de auth/escopo Odoo (`verificar_token` + `get_cliente_servico`) dos endpoints existentes; novo `real/alarmApi.ts` no frontend |
| "Registro íntegro" (selo do topbar) | sem endpoint | **assumção a validar na revisão**: não implementar verificação criptográfica ao vivo nesta fatia — tratar como health flag simples (API alcançável + últimas leituras chegando assinadas), não uma auditoria de cadeia de ledger em tempo real. Se o usuário quiser a verificação forte, isso é um projeto à parte. |
| Pill da unidade (nome do hospital) | sem campo | adicionar ao retorno do login (`authApi`) ou a um novo campo em `metaApi` — a definir na task correspondente |

## 6. Interações e comportamento

Herda o comportamento já descrito no handoff (`README.md` do pacote):
clicar card seleciona área; clicar linha de sensor seleciona
área+sensor e atualiza o painel de detalhe; botões de métrica trocam
sensor mantendo área; toggle Ao vivo/Dia todo troca janela do gráfico;
hover no gráfico mostra tooltip; alternância de tema troca classe no root;
novo alarme → topo da lista + toast + badge no card; normalização → evento
+ toast, badge do dia permanece. Transições 120–180ms, sem spring/bounce
(mantém regra de UI de monitoramento contínuo já em vigor no projeto).

## 7. Acessibilidade

Mantém as regras já validadas no `PRODUCT.md`/`DESIGN.md` atual — não são
negociáveis pela troca de skin: WCAG AA em ambos os temas, alvos de toque
≥44px em todo controle (CME operada com luvas), estado nunca só por cor
(forma do ícone + cor + texto), `focus-visible` em vez de `:focus`,
`motion-reduce:transition-none` nas transições.

## 8. Testes

Mesma disciplina das fatias anteriores (verificação visual real pegou 3
bugs reais até agora — ECharts `appendData`+line, `color-mix` de matiz,
`ThemeToggle` ausente): suite de unit/component tests por peça +
verificação visual manual em ambos os temas, mobile e desktop, antes de
marcar qualquer task como concluída.

## 9. Riscos / pontos a validar na revisão

- Fusão de 3 telas em 1 pode ficar densa em telas estreitas — o handoff já
  prevê `flex-wrap` para o painel de alarmes descer abaixo dos cards sem
  media query; validar que cards+detalhe também degradam bem antes de dar
  como pronto.
- "Registro íntegro" como health flag simplificado (§5) é uma redução de
  escopo da minha parte — confirmar que é isso mesmo que o usuário quer, não
  uma verificação criptográfica real da cadeia de ledger.
- Polling para o modo "Ao vivo" (em vez de streaming) é uma escolha de
  simplicidade por ora — se a cadência de 1 leitura/s por sensor com vários
  sensores abertos ficar pesada, reavaliar para SSE.
