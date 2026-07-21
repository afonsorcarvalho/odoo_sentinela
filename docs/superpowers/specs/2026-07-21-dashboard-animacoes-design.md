# Animações da dashboard — design

**Data:** 2026-07-21
**Status:** aprovado (brainstorm) → pronto p/ plano de implementação
**Escopo:** frontend SPA Sentinela (`frontend/`), dashboard de monitoramento CME.

## Objetivo

Elevar a UX da dashboard com **micro-interações de deleite/polish**, no nível de
intensidade **equilibrado**: movimento notável mas contido, que dá sensação
premium sem distrair do dado crítico (contexto industrial de monitoramento
contínuo). Não é sobre feedback de dados nem performance percebida — é polimento.

## Princípios transversais (aplicam a TODAS as superfícies)

1. **`prefers-reduced-motion` sempre respeitado.** Cada efeito degrada para troca
   instantânea (sem `transform`, sem keyframe de entrada). Reusar o hook
   existente `usePrefersReducedMotion` (`frontend/src/lib/useSensorCarousel.ts`)
   e a variante utilitária `motion-reduce:` do Tailwind (já usada no código, ex:
   `AreaCard.tsx`, `WindowSelector.tsx`).
2. **Tokens de motion centralizados.** Adicionar durações e easings ao bloco
   `@theme` em `frontend/src/index.css`, para consistência e um só ponto de
   ajuste. Nomes propostos:
   - `--ease-out-soft: cubic-bezier(.22,.61,.36,1)` (entradas)
   - `--ease-in-soft: cubic-bezier(.55,.06,.68,.19)` (saídas)
   - `--ease-overshoot: cubic-bezier(.34,1.5,.64,1)` (knob do tema, bump)
   - `--dur-fast: 180ms` · `--dur-base: 300ms` · `--dur-slow: 400ms`
3. **Sem nova dependência.** Nada de framer-motion/`motion`. Todos os efeitos são
   keyframes CSS + `transition` + um hook `useCountUp` (rAF, ~15 linhas). Mantém
   o bundle intacto e casa com o padrão atual do código. (Decisão: abordagem A
   vs. B `motion` — B rejeitada por +~35kb e overkill p/ nível "equilibrado".)

## Superfícies

### 1. Carrossel de sensores (`AreaCard.tsx`)

Hoje `useSensorCarousel` troca o sensor ativo instantaneamente (só
`transition-colors`). Adicionar transição na troca:

- **Movimento:** cross-fade + subida de 8px. O valor que sai faz fade-out; o que
  entra surge subindo 8px com fade-in. Sem deslize lateral (variação "B"
  escolhida sobre slide horizontal e slide+spring).
- **Timing:** entrada 300ms `--ease-out-soft`; saída 220ms `--ease-in-soft`.
- **Dots indicadores:** mover de rodapé horizontal centralizado para **coluna
  vertical à esquerda do valor, centralizada na altura** (`flex-col`, centrado).
  Dot ativo: `background var(--color-ink)` + leve `scale(1.15)`; inativos
  `var(--color-line)`.
- **Reduced-motion:** troca instantânea; dots continuam funcionais.
- **Nota de implementação:** a troca cross-fade precisa que os slots entrando e
  saindo coexistam brevemente (posição absoluta sobreposta) — usar key por
  `sensor_code` para o React remontar, ou controlar via classe `enter`/`leave`.

### 2. Widgets — entrada no load + hover (`DashboardPage` / `WidgetFrame.tsx`)

- **Entrada:** cada widget entra com fade + subida de 14px, **escalonado ~70ms**
  entre widgets (ordem do layout). Duração 400ms `--ease-out-soft`. Ocorre uma
  vez no mount da grade.
- **Hover:** eleva **5px** (`translateY(-5px)`) + sombra
  (`0 10px 26px rgba(0,0,0,.4)` no dark / equivalente claro) + `border-color`
  levemente mais forte. Transição 220ms.
- **Reduced-motion:** sem stagger nem elevação (opacidade direta; hover só muda
  sombra/borda, sem transform).
- **Nota:** o stagger index vem da ordem de `react-grid-layout`. Não animar
  reflow durante drag/resize no editor — só a entrada inicial.

### 3. Alarme ao vivo chegando (`AlarmsWidget.tsx` / `AlarmPanel.tsx`)

- **Movimento:** novo alarme entra deslizando do topo (`translateY(-12px)`) +
  fade, inserido no topo da lista. Entrada 320ms `--ease-out-soft`.
- **Flash de destaque:** após entrar, fundo pisca em tom de status suave
  (crit/warn-soft) e **desvanece ao longo de 5s** até o fundo normal. O alarme
  **permanece** na lista (é condição ativa — nunca auto-remover).
- **Reduced-motion:** aparece sem slide; flash vira um realce estático breve ou
  nenhum (aceitável remover o flash em reduced-motion).
- **Nota:** identificar "novo" por diff de IDs entre renders (alarmes que não
  estavam na lista anterior). Cuidar p/ não re-disparar flash em re-render sem
  mudança real.

### 4. KPI — novo valor (`KpiWidget.tsx`)

- **Count-up:** ao mudar o valor, animar do valor anterior ao novo via `rAF`
  (easing cubic-out), ~550ms. Hook novo `useCountUp(value)`.
- **Bump:** número dá um `scale(1.12)` breve com cor `--color-warn` no pico,
  voltando ao normal (`--ease-overshoot`, 400ms).
- **Reduced-motion:** valor troca direto, sem count-up nem bump.
- **Nota:** respeitar casas decimais/formatação existente do KPI durante a
  interpolação (tabular-nums já em uso).

### 5. Drill-down — painel de detalhe (`SensorDetailDrawer.tsx` / `SensorDetailPanel.tsx`)

- **Responsivo:** desktop = painel lateral desliza da **direita**
  (`translateX(100%)→0`); mobile = **bottom sheet** sobe de baixo
  (`translateY(100%)→0`). Breakpoint conforme o resto do app.
- **Backdrop:** overlay escurece atrás com fade (`opacity 0→1`, 280ms). Clique no
  backdrop fecha.
- **Timing:** painel 320ms `--ease-out-soft` (abrir) / `--ease-in-soft` (fechar).
- **Reduced-motion:** aparece/some sem slide (só fade do backdrop e do painel).
- **Nota:** já existe resolução de `outsidePress`/foco no drawer atual — preservar
  esse comportamento; a animação é só camada visual sobre o toggle de estado.

### 6. Chips de filtro (`AlarmsWidget` filtro / componente de chips)

- **Tap:** `active:scale(.94)` (90ms) + transição de cor/borda (180ms) ao alternar
  estado. Mantém tap target ≥44px já existente.
- **Reduced-motion:** sem scale; só troca de cor.

### 7. Toggle de tema (`ThemeToggle.tsx`)

- **Knob:** desliza entre posições com leve overshoot (`--ease-overshoot`, 300ms).
- **Reduced-motion:** desliza sem overshoot (ou troca direta).

### 8. Modo editor (`DashboardPage` editor / grid overlay)

- **Grid overlay:** ao entrar em edição, aparece um grid de fundo com fade (300ms).
- **Wobble "arrastável":** widgets fazem um balanço rotacional sutil
  (`rotate ±0.4deg`, loop lento ~1.8s, delays escalonados) sinalizando que são
  arrastáveis. Só no modo edição.
- **Handle de resize:** aparece com fade.
- **Reduced-motion:** grid overlay aparece sem fade; **sem wobble** (movimento
  contínuo é o mais problemático p/ reduced-motion — desligar).

## Arquitetura / unidades

- **Tokens** (`index.css @theme`): fonte única de durações/easings. Adicionados no
  bloco `@theme`; herdados por claro e `.theme-control` (não dependem de cor).
- **`useCountUp(value: number)`** (`frontend/src/lib/useCountUp.ts`): hook isolado,
  retorna valor interpolado; respeita reduced-motion (retorna valor final direto).
  Testável em unidade sem DOM de animação.
- **Keyframes CSS** globais em `index.css` (`@keyframes` + classes utilitárias
  como `.animate-widget-in`, `.animate-alarm-in`) reutilizáveis; ou classes
  Tailwind inline onde simples. Preferir classes nomeadas p/ keyframes complexos
  (carrossel, alarme, wobble).
- **Sem estado global novo.** Cada efeito é local ao componente. Carrossel já tem
  seu hook; só ganha classes de transição.

## Testes

- **Unit (`useCountUp`):** com reduced-motion → retorna valor final imediatamente;
  sem → converge ao alvo. Mockar matchMedia.
- **Componentes:** os testes existentes (AreaCard, AlarmsWidget, KpiWidget,
  SensorDetail*) não devem quebrar. Animação é aditiva; asserts de conteúdo/aria
  seguem válidos. Verificar que a mudança de layout dos dots do carrossel
  (rodapé→lateral) não quebra o `role="tablist"`/`aria-selected` existente.
- **Reduced-motion:** onde há teste com matchMedia mockado, cobrir o ramo de
  degradação (sem transform/keyframe).
- **Visual (Playwright):** verificação manual/roteirizada das 8 superfícies no
  browser (padrão do projeto: chrome-devtools não sobe em WSL2, usar Playwright).

## Fora de escopo (YAGNI)

- Framer-motion / lib de animação.
- Animação de reflow do grid durante drag/resize (só entrada inicial anima).
- Parallax, transições de rota de página inteira, animação de gráficos ECharts
  além do que a lib já faz.
- Auto-dismiss de alarmes.

## Decisões registradas

- Transição do carrossel: **B (cross-fade + subida)**, não slide lateral nem spring.
- Dots do carrossel: **coluna vertical à esquerda, centralizada**.
- Hover de widget: **5px** (testado 3/10, escolhido 5).
- Flash do alarme novo: **5s**, alarme permanece.
- Drill-down: **responsivo** (direita desktop / bottom mobile).
- Implementação: **CSS/Tailwind + hooks**, sem dependência nova.
