# Design: Error boundary por widget (A1)

## Contexto

No dashboard customizável (`DashboardGrid` → `WidgetFrame` → `descriptor.render(widget)`),
cada widget é renderizado dentro de um `WidgetFrame` no grid do react-grid-layout. Hoje,
se qualquer widget lançar durante o render (bug de acesso a dado indefinido, tipo
inesperado, erro numa lib de gráfico), o erro sobe pela árvore e **derruba o dashboard
inteiro** — todos os vizinhos somem e o admin fica sem tela. Objetivo: isolar cada widget
para que um render quebrado mostre um fallback local e não afete os demais.

Verificado antes de escrever: não existe nenhum error boundary no projeto
(`grep componentDidCatch|getDerivedStateFromError|ErrorBoundary` → 0 resultados) e
`react-error-boundary` **não** é dependência (`react ^19.2.7`).

## Decisão de abordagem

**Componente class próprio** (`WidgetErrorBoundary`, `~40 linhas`), não a lib
`react-error-boundary`. Motivo: o React 19 ainda não tem API de error boundary em hook —
exige `componentDidCatch`/`getDerivedStateFromError`, que só existem em class component. A
única escolha real é lib vs. class à mão. Seguindo o mesmo critério da spec do carrossel
(evitar dependência não usada em nenhuma outra parte do projeto para um requisito simples),
a lib não se justifica: precisamos só de capturar, mostrar fallback e resetar — sem
`resetKeys`/`onReset`/fallback-render-props sofisticados que a lib oferece.

## Comportamento

### Onde envolve

- O boundary envolve **apenas o filho de render do widget** — o
  `<div className="min-h-0 flex-1">{descriptor.render(widget)}</div>` dentro do
  `WidgetFrame`. **Não** envolve o `WidgetFrame` inteiro.
- **Restrição load-bearing:** o chrome de edição (botões ⚙ Configurar / ✕ Remover, que
  ficam no `WidgetFrame` acima do conteúdo) tem de permanecer **fora** do boundary. Se o
  widget quebrado levasse junto o próprio botão de remover, o admin não conseguiria apagar
  a tile quebrada e o dashboard ficaria preso com um widget irremovível.
- **Guarda de tipo desconhecido:** `WIDGET_REGISTRY[widget.type]` pode ser `undefined`
  (tipo salvo no layout que não existe mais no registry). Esse acesso e o uso de
  `descriptor.label` ficam *acima* do boundary e crashariam o `WidgetFrame`. O `WidgetFrame`
  deve guardar `if (!descriptor)` e renderizar um `WidgetPlaceholder` antes de usá-lo.

### Fallback UI (no lugar do widget quebrado)

- Ocupa a área do widget (`h-full`), visual coerente com `WidgetPlaceholder` (borda,
  `text-xs`, tokens de tema), porém em cor de erro (`var(--color-crit)` ou equivalente).
- Conteúdo: mensagem curta ("Widget indisponível"), o **rótulo do tipo**
  (`descriptor.label` — ex.: "Gráfico temporal") passado como prop pelo `WidgetFrame`, e um
  botão **"Recarregar widget"**.
- "Recarregar widget" reseta o estado de erro do boundary (`setState({ error: null })`),
  forçando novo mount/render do widget.

### Isolamento render vs. dado

- Confirmado nos widgets (`AreaWidget`, `KpiWidget`, etc.): os dados vêm de react-query, que
  expõe falha como estado (`isError`/`error`) e **não lança durante o render**. Logo o
  boundary **não** captura falha de fetch — essa continua tratada dentro do widget
  (padrão atual do `WidgetPlaceholder`/estados de loading).
- O boundary é **backstop para crashes inesperados de render**, não substituto dos estados
  de loading/erro/vazio de cada widget. Fase-1 **não** liga `throwOnError` do react-query —
  os dois mecanismos ficam separados de propósito.

### Reset ao reconfigurar

- Além do botão, **reconfigurar o binding/options via popover deve limpar o erro**. Um
  boundary que só reseta pelo botão deixaria o widget quebrado mesmo depois de o admin
  corrigir a configuração.
- Solução: dar `key` ao boundary derivada de `widget.binding` + `widget.options` (ex.:
  `JSON.stringify`), para o React remontar limpo quando a config muda.

### Log

- `componentDidCatch` chama `console.error` com `widget.id`, `widget.type` e o
  `componentStack`. Sem telemetria remota nesta fase.

### Modo edição vs. view

- Comportamento do fallback é idêntico nos dois modos.
- Diferença: em modo edição os botões ⚙/✕ do `WidgetFrame` continuam visíveis e funcionais
  (por estarem fora do boundary) — permitindo reconfigurar ou remover a tile quebrada. Em
  modo view, só o fallback + "Recarregar widget".

## Testes a cobrir

- **Headline:** dois widgets no grid, um lança no render → o vizinho continua renderizado
  **e** o fallback mostra o rótulo do widget quebrado (suprimir o `console.error` esperado).
- "Recarregar widget" reseta o boundary (widget que parou de lançar volta a renderizar).
- Reconfigurar binding/options limpa o erro (remonta via `key`).
- Falha de dado (react-query `isError`) **não** dispara o boundary — segue no estado
  in-widget.
- Remover um widget quebrado em modo edição funciona (botão ✕ fora do boundary).
- Tipo desconhecido no layout → `WidgetPlaceholder`, sem crash do `WidgetFrame`.

## Fora de escopo (fase 1)

- Telemetria remota do erro (Sentry / sink no Odoo) — só `console.error`.
- Retry automático / backoff no fallback.
- Fallback customizado por tipo de widget (um único fallback genérico serve).
- Rotear erros de dado (react-query) para o boundary via `throwOnError`.
- Boundary de nível de app (fora do grid) — esta spec é só por widget.
