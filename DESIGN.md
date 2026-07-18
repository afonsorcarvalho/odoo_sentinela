---
name: Sentinela CME
description: Dashboard de monitoramento de conformidade regulatória (RDC 15) para CME hospitalar
colors:
  bg: "oklch(0.99 0.002 245)"
  surface: "oklch(1 0 0)"
  panel: "oklch(0.975 0.003 245)"
  ink: "oklch(0.24 0 none)"
  muted: "oklch(0.52 0.01 245)"
  line: "oklch(0.92 0.004 245)"
  primary: "oklch(0.55 0.13 245)"
  good: "oklch(0.62 0.15 150)"
  warn: "oklch(0.68 0.15 75)"
  crit: "oklch(0.55 0.19 25)"
typography:
  display:
    fontFamily: "Geist Mono, ui-monospace, SF Mono, Menlo, monospace"
    fontSize: "clamp(3rem, 4vw, 3.75rem)"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "-0.02em"
  title:
    fontFamily: "system sans-serif stack (Tailwind default)"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "normal"
  body:
    fontFamily: "system sans-serif stack (Tailwind default)"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "Geist Mono, ui-monospace, SF Mono, Menlo, monospace"
    fontSize: "0.6875rem"
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: "0.02em"
rounded:
  sm: "4px"
  md: "8px"
  lg: "12px"
  xl: "16px"
  full: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "28px"
components:
  badge-alarm-count:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.crit}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
  badge-regulatory:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.primary}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  card-area:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.xl}"
    padding: "20px"
  readout-panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.xl}"
    padding: "24px 28px"
  segmented-control:
    backgroundColor: "{colors.panel}"
    rounded: "{rounded.lg}"
    padding: "4px"
  segmented-control-active:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.md}"
---

# Design System: Sentinela CME

## 1. Overview

**Creative North Star: "O Instrumento de Bancada"**

Sentinela CME não é um SaaS querendo parecer confiável — é instrumentação clínica que precisa *ser* confiável. A referência não é o painel de métricas de produto, é o instrumento de bancada de laboratório: leitura numérica grande e monoespaçada, faixa de tolerância desenhada com precisão, estado codificado por forma **e** cor (nunca só cor), superfícies planas separadas por linha fina, nunca por sombra decorativa. Nada aqui está "vendendo" a leitura; está reportando.

O sistema rejeita explicitamente o clichê de dashboard SaaS: nada de hero-metric com gradiente, nada de cards idênticos em grade genérica, nada de vidro (glassmorphism) ou texto em gradiente. Cor de status é a linha vermelha do produto (ver a técnica `oklch(... none)` na seção 2) — nunca decoração, sempre sinal.

Densidade é deliberadamente baixa a maior parte do tempo (a tela fica "de fundo" enquanto tudo está OK) e sobe apenas quando o estado exige atenção — o ícone de estado (círculo/triângulo/quadrado/tracejado) muda de forma, não só de cor, para não depender de percepção cromática sozinha.

**Key Characteristics:**
- Leitura numérica ao vivo em mono, grande, `tabular-nums` — nunca sans-serif proporcional para valores.
- Estado codificado por forma do ícone + cor de texto derivada (`color-mix` com `--color-ink`, nunca o tom puro do token), garantindo AA em ambos os temas.
- Superfícies planas, delimitadas por `--color-line` (1px), sem sombra ambiente.
- Alvos de toque ≥44px (`min-h-11`/`min-w-11`) em todo controle interativo — ambiente de CME é operado com luvas.
- Tema claro e escuro são cidadãos de primeira classe, não um invertido automático — cada token tem par claro/escuro calibrado à mão.

## 2. Colors

Paleta contida, quase monocromática (bg/surface/panel/ink/muted/line no mesmo matiz 245°), com três cores de status vivas como único ponto de saturação real da interface.

### Primary
- **Azul Instrumento** (`oklch(0.55 0.13 245)` claro / `oklch(0.70 0.13 245)` escuro): ações e seleção ativa — chip de janela temporal selecionado, foco, link de card. Usado com moderação; não é decoração, é "isto é interativo/selecionado".

### Status (papel próprio — não é Secondary/Tertiary genérico)
- **Bom** (`oklch(0.62 0.15 150)` claro / `oklch(0.72 0.16 150)` escuro): dentro de faixa seletada.
- **Alerta** (`oklch(0.68 0.15 75)` claro / `oklch(0.78 0.15 75)` escuro): próximo do limite (dentro da margem de alerta).
- **Crítico** (`oklch(0.55 0.19 25)` claro / `oklch(0.68 0.20 25)` escuro): fora de faixa regulatória.

### Neutral
- **Fundo** (`oklch(0.99 0.002 245)` claro / `oklch(0.16 0.008 245)` escuro): tela.
- **Superfície** (`oklch(1 0 0)` claro / `oklch(0.21 0.01 245)` escuro): cards, painéis de leitura.
- **Painel** (`oklch(0.975 0.003 245)` claro / `oklch(0.19 0.009 245)` escuro): fundo de badge e do trilho do seletor de janela — um degrau mais recuado que Superfície.
- **Tinta** (`oklch(0.24 0 none)` claro / `oklch(0.95 0 none)` escuro): texto principal.
- **Neutro-atenuado** (`oklch(0.52 0.01 245)` claro / `oklch(0.68 0.01 245)` escuro): texto secundário, unidades, rótulos.
- **Linha** (`oklch(0.92 0.004 245)` claro / `oklch(0.30 0.01 245)` escuro): toda borda/divisor — a única forma de separação de superfície neste sistema.

### Named Rules
**The Powerless Hue Rule.** Tinta usa `oklch(L 0 none)`, não `oklch(L 0 0)`. `none` marca o matiz como ausente (CSS Color 4); `0` é um matiz azulado explícito a 0°. Misturar cor de status com tinta via `color-mix(in oklch, ...)` quando tinta carrega um matiz explícito faz a interpolação cruzar a roda de cores pelo lado errado — crítico (25°) virava roxo (329°), alerta (75°) virava verde (143°), podendo ser confundido com o estado "bom". Todo `color-mix` envolvendo tinta e um token de status é proibido sem `none`.

**The Status-Is-Never-Raw Rule.** Nenhum token `--color-good` / `--color-warn` / `--color-crit` é usado puro como cor de texto — sempre misturado 60% token / 40% `--color-ink` (`statusVisuals.tsx`) para atingir AA. O token puro só aparece em elementos gráficos não-textuais (ponto do trilho, ícone preenchido) onde o rótulo textual ao lado já carrega o contraste.

## 3. Typography

**Display/Readout Font:** Geist Mono (com fallback `ui-monospace, SF Mono, Menlo, monospace`)
**Body Font:** stack sans padrão do sistema (via Tailwind), sem família customizada
**Label/Mono Font:** Geist Mono, mesma família do readout

**Character:** Um único par de vozes: mono para todo dado numérico (leitura, unidade de eixo, ticks de faixa), sans do sistema para tudo que é rótulo/prosa. Não há terceira família — a mono é o "instrumento", a sans é a "legenda".

### Hierarchy
- **Display** (600, `clamp(3rem, 4vw, 3.75rem)`/`text-5xl md:text-6xl`, leading-none, mono, tabular-nums, tracking-tight): valor ao vivo do sensor — o único elemento que domina a tela.
- **Title** (600, `1rem`/`text-base`): nome da área/card (`AreaCard`).
- **Body** (400, `0.875rem`/`text-sm`): texto corrido, faixa segura, rótulos de estado.
- **Label** (500, `0.6875rem`–`0.75rem`/`text-[11px]`–`text-xs`, mono ou uppercase tracking-wide): unidade (`text-lg uppercase tracking-wide`), badges, ticks min/max do trilho (sempre mono, `tabular-nums`).

### Named Rules
**The Numeric-Is-Mono Rule.** Todo número que representa uma leitura de sensor (valor ao vivo, min/max do trilho, faixa) é mono + `tabular-nums`. Números em prosa (contagem de alarmes: "2 alarmes") ficam na sans do rótulo — a mono é reservada ao dado de instrumento, não a qualquer dígito na tela.

## 4. Elevation

Sistema estritamente plano — nenhuma sombra ambiente foi encontrada no código. Profundidade é comunicada só por `--color-line` (borda de 1px) e por diferença de tom entre `--color-bg` / `--color-panel` / `--color-surface` (três neutros muito próximos, degraus sutis). A única ocorrência de `box-shadow` no projeto é um anel rígido de 2 camadas (`0 0 0 2px superfície, 0 0 0 3px linha`) que destaca o ponto do trilho de tolerância contra o próprio trilho — não é elevação, é um contorno de precisão.

### Named Rules
**The Flat-By-Default Rule.** Nenhuma superfície recebe `box-shadow` para indicar elevação. Se uma superfície precisa se destacar, o recurso é borda (`--color-line`) ou um degrau de tom entre `bg`/`panel`/`surface` — nunca sombra.

## 5. Components

### Buttons / Controles de toque
- **Shape:** `rounded-md` (8px) para itens de segmented control; `rounded-lg` (12px) para o contêiner.
- **Alvo de toque:** `min-h-11 min-w-11` (44px) em todo controle — não-negociável neste produto (CME operado com luvas).
- **Ativo:** fundo `--color-primary`, texto `--color-surface` (a polaridade certa em ambos os temas — branco fixo falharia AA no escuro).
- **Inativo:** texto `--color-muted`, hover para `--color-ink`.
- **Focus:** anel de 2px em `--color-primary`, offset — sempre `focus-visible`, nunca `:focus` puro.
- **Motion:** `transition-colors duration-200 ease-out`, com `motion-reduce:transition-none` em todo componente interativo.

### Chips / Badges
- **Contagem de alarme:** `rounded-full`, fundo `--color-panel`, texto `--color-crit`, `text-xs font-semibold`, padding `2px 8px`.
- **Selo regulatório (RDC 15):** `rounded` (4px, mais reto que os chips de contagem — deliberadamente menos arredondado, lê como "carimbo" e não como tag social), fundo `--color-panel`, texto `color-mix(in oklch, var(--color-primary) 70%, var(--color-ink) 30%)` (a mistura pura de primary falha AA por pouco: 4.48:1 vs mínimo 4.5:1).

### Cards / Containers
- **Corner Style:** `rounded-2xl` (16px) — cards de área e painel de leitura ao vivo.
- **Background:** `--color-surface`.
- **Shadow Strategy:** nenhuma; ver Elevation.
- **Border:** `1px solid var(--color-line)` em repouso; muda para `--color-primary` no hover do card clicável (`AreaCard`).
- **Internal Padding:** `p-5` (cards de área), `p-6 md:p-7` (painel de leitura, mais respiro por carregar o dado display).

### Inputs / Fields
- Não há campo de texto livre neste sistema ainda; seleção é via segmented control (`WindowSelector`), não input.

### Navigation
- Toggle de tema: botão outline (`border: 1px solid var(--color-line)`), ícone sol/lua com o mesmo vocabulário gráfico stroke-based dos ícones de status (16×16, `strokeWidth 1.6`) — deliberado, para não introduzir um segundo sistema de ícones na página.

### Tolerance Rail (componente de assinatura)
Trilho horizontal de 1.5px de altura que codifica a leitura como posição (não só como cor): trilho neutro (`--color-line`) com uma banda verde translúcida (`opacity: 0.2`) marcando a faixa seletada entre as margens de alerta, ponto de 14px na posição da leitura (cor = estado), e um indicador triangular "pinado" quando o valor estoura a escala. Ticks de min/max sempre em mono `text-[11px] tabular-nums`. Esta é a peça central da identidade visual do produto — todo elemento novo de "faixa/limite" deve reusar este vocabulário, não inventar um novo.

## 6. Do's and Don'ts

### Do:
- **Do** usar mono + `tabular-nums` para todo valor numérico de sensor (leitura, ticks, faixa).
- **Do** misturar cor de status com `--color-ink` (60/40) antes de usar como texto — nunca o token puro.
- **Do** usar `oklch(L 0 none)` para tinta/neutros que participam de `color-mix` com cores de status.
- **Do** manter alvos de toque ≥44px (`min-h-11`/`min-w-11`) em todo controle.
- **Do** comunicar estado por forma do ícone **e** cor — nunca só cor.
- **Do** separar superfícies com `1px solid var(--color-line)` ou degrau de tom, nunca sombra.
- **Do** incluir `motion-reduce:transition-none` em toda transição.

### Don't:
- **Don't** usar hero-metric template, gradiente em texto, ou glassmorphism decorativo — este produto reporta estado real, não vende uma métrica de vaidade.
- **Don't** repetir grades de cards idênticas como resposta padrão a "preciso listar N coisas".
- **Don't** aplicar `box-shadow` como elevação — o sistema é estritamente plano.
- **Don't** usar o token de status puro (`--color-good`/`warn`/`crit`) como cor de texto — sempre a mistura com ink.
- **Don't** introduzir uma segunda família de fonte além de Geist Mono (dado) + sans do sistema (rótulo/prosa).
- **Don't** confiar só em cor para indicar estado de alarme — é o bug real já cometido neste projeto (interpolação de matiz do `color-mix` invertendo crítico↔ok).
