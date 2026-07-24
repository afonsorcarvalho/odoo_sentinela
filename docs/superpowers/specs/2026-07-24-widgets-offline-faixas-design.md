# Widgets do dashboard: sinal de sensor offline + faixas fora-de-limite

Data: 2026-07-24
Escopo: `frontend/src/components/` (widgets KPI e Timeseries, TimeSeriesChart, chartOption)

## Problema

Dois buracos de sinalização nos widgets do dashboard customizável:

1. **Sensor offline invisível.** `KpiWidget` e `TimeseriesWidget` mostram o último
   dado recebido sem indicar a idade dele. Um sensor parado há 40 minutos aparece
   com o número brilhante, na cor de estado (inclusive `crit` vermelho), idêntico
   a uma leitura de 3 segundos atrás. O `AreaCard` já resolve isto (badge de
   frescor + marcador de área), mas os widgets do dashboard não herdaram nada.
2. **Excursões passadas invisíveis.** O gráfico temporal desenha as linhas de
   limite (`markLine`) e a faixa verde de conformidade (`markArea` em Y), mas nada
   marca *quando* a série esteve fora do limite. Numa janela de 24 h ou 30 d, um
   pico que saiu da faixa e voltou é fácil de perder.

## Decisões

| Questão | Decisão |
|---|---|
| Fonte do "offline" | `freshness(live, now)` (idade do dado), **não** `LiveConnectionState` |
| KPI em stale/offline | Badge de frescor + número atenuado (muted) |
| Chart em stale/offline | Badge no header + faixa cinza de silêncio no gráfico |
| Fonte das faixas fora-limite | Derivada dos pontos plotados (cliente), não `alarm_event` |
| Semântica em janela agregada | Compara o valor plotado (`avg`) |
| Acima vs abaixo do limite | Mesma cor `crit`; direção só no label de hover |

### Por que `freshness()` e não `LiveConnectionState`

São dois conceitos distintos e o código já documenta a diferença
(`lib/types.ts:47-50`): `LiveConnectionState` vem exclusivamente de
`onopen`/`onerror`/`readyState` do EventSource e **nunca** da chegada de dado,
porque silêncio de dados é normal neste backend. "Sensor offline" é justamente
o silêncio de dados — logo, `freshness()`, que classifica `now - live.ts` em
`fresh | stale | offline | never` (thresholds 5 min / 15 min).

### Por que faixas derivadas e não `alarm_event`

`alarm_event` é autoritativo (é a verdade dos alarmes e relatórios) mas exigiria
endpoint novo e pode divergir visualmente da linha desenhada por dead-band ou
histerese — faixa vermelha sem excursão visível por baixo lê como bug. Derivar
dos pontos plotados dá coerência garantida com o que o usuário vê, zero API nova,
e segue o precedente de `KpiWidget.foraDaFaixa` (`widgets/KpiWidget.tsx:49`).

## Arquitetura

### Regra transversal: `now` é sempre injetado

Nenhuma das funções puras chama `Date.now()`. `now` entra por parâmetro
(funções) ou por prop (componentes), vindo de `useNow()` no caminho real e de
valor fixo em teste. Mesma regra que `freshness()` já segue
(`lib/freshness.ts:18-25`).

Consequência não-óbvia e obrigatória: **os widgets precisam chamar `useNow()`**.
Sem ele o componente não re-renderiza enquanto o sensor está mudo, e a transição
`fresh → stale → offline` nunca aparece na tela — o relógio andando é o único
evento. É por isso que `AreaCard.tsx:135` chama `useNow()`.

### Parte 1 — sinal de sensor offline

**`KpiWidget`**

- Passa a chamar `useNow()` e derivar `tier = freshness(last, now)`.
- Header vira linha flex: título à esquerda, `<FreshnessBadge tier ageMs />` à
  direita. `FreshnessBadge` não renderiza em `fresh` (o chamador não o monta).
- `tier !== 'fresh'` → cor do número vira `var(--color-muted)` com `opacity: .7`.
  A atenuação **vence** a cor de estado, inclusive o `crit` produzido pelo
  override `limiteMin`/`limiteMax`: um número velho não pode gritar vermelho como
  se fosse leitura atual. A lógica de `maisSevero`/`foraDaFaixa` fica intacta;
  só o cálculo final de `cor` ganha o curto-circuito por tier.
- `never` (nenhum `LivePoint` ainda): já mostra `—`; o badge diz "aguardando dado".

**`TimeseriesWidget` / `TimeSeriesChart`**

- `TimeseriesWidget` chama `useNow()` e já usa `useLiveTail`; o tier vem de
  `freshness(last, now)` — o mesmo `last` que o KPI usa, não o fim da cauda.
  Renderiza `<FreshnessBadge>` no header entre o nome do sensor e o
  `WindowSelector`, e passa `now` para `TimeSeriesChart`.
- `TimeSeriesChart` ganha prop `now?: number` e repassa a `buildChartOption`.
- Faixa de silêncio: `markArea` em X do timestamp do **último ponto da série
  desenhada** (`data` já mesclada histórico + cauda) até `now`, em
  `--color-muted` com opacity baixa. O gatilho é calculado dentro de
  `buildChartOption` a partir de `now` e do último ts: desenha se
  `now - ultimoTs > DEFAULT_STALE_MS` (equivalente aos tiers `stale`/`offline`,
  reusando a constante de `lib/freshness.ts` em vez de receber o tier por
  parâmetro). Se `data` está vazia, ou se `now` não foi passado, não há faixa —
  sem ponto não existe início confiável. A severidade fica no badge; a faixa só
  afirma "sem dado aqui". Isto mostra *quando* o sensor parou, não apenas *que*
  parou.
- Tier `never` (sem `LivePoint`): badge "aguardando dado". A faixa de silêncio
  **pode aparecer mesmo assim** — o gatilho é o gap de `data`, não o tier, e o
  caso concreto é o dashboard abrindo com um sensor parado há 1 h: o histórico
  termina 1 h atrás e a cauda ao vivo está vazia. Badge "aguardando dado" +
  faixa cinza cobrindo a última hora é a leitura correta da situação; badge
  sozinho esconderia o buraco.

### Parte 2 — faixas de tempo fora-de-limite

Função pura nova em `components/chartOption.ts`, exportada e testada isoladamente:

```ts
export type Banda = { inicio: number; fim: number; direcao: 'acima' | 'abaixo' }

export function computeOutOfRangeBands(
  data: [number, number][],   // pontos já plotados (ts, valor), ordenados
  threshold: Threshold,
): Banda[]
```

Regras:

- **Limite**: `threshold` do cadastro do sensor (a mesma fonte do `markLine`).
  Nunca o override `limiteMin`/`limiteMax` do KPI — esse é display-only por
  widget e existe para outro propósito.
- **Valor comparado**: o valor já plotado. Em janela agregada isso é `avg`
  (`chartOption.ts:25`), então toda faixa tem uma excursão visível da linha por
  baixo dela. Picos curtos diluídos pela média não geram faixa — aceito em
  troca de nunca pintar faixa "sem motivo aparente".
- **Runs**: pontos contíguos fora do limite formam uma banda. Troca de direção
  (acima → abaixo sem passar por dentro) fecha a banda e abre outra.
- **Ponto isolado**: um único ponto fora produz banda de largura zero, invisível.
  Cada extremo é estendido até o meio-caminho do vizinho imediato; sem vizinho
  daquele lado (ponto na borda da série), usa metade do espaçamento mediano.
- **Gap de dados**: se o intervalo entre dois pontos fora-de-limite consecutivos
  for maior que 3× o espaçamento mediano da série, a banda quebra em duas. Sem
  isto, um silêncio de horas entre duas leituras altas viraria uma banda contínua
  afirmando algo que não foi medido.
- `threshold` ausente → `[]`.

Render em `buildChartOption`:

- Vermelho suave (`--color-crit`, opacity baixa), igual para acima e abaixo. A
  direção já é óbvia pela posição da linha e aparece no label de hover no formato
  `acima do limite · 14:05–14:32`.
- **Composição do `markArea`**: `markArea` é único por série, e hoje já carrega a
  faixa verde de conformidade em Y (`chartOption.ts:52`). As três origens
  (faixa verde em Y, faixas vermelhas em X, faixa cinza de silêncio) entram no
  mesmo `data[]`. O `itemStyle` sai do root do `markArea` e desce para cada item,
  já que agora cada par tem cor própria. Ordem no array: verde primeiro
  (fundo), depois vermelhas, depois cinza.
- Cores resolvidas por `useThemeColor` em `TimeSeriesChart` e passadas já
  concretas — ECharts pinta em `<canvas>` e não resolve `var(...)`
  (`chartOption.ts:6-15`).

Duas notas de implementação, achadas na revisão do spec:

- O label de hover precisa de `emphasis.label` com o texto **pré-formatado no
  `name` do item**. Um `formatter` não enxerga facilmente o par início/fim da
  faixa, então a string `acima do limite · 14:05–14:32` é montada ao construir
  o item, não no render.
- A faixa verde de conformidade (opacity 0.5) e as faixas vermelhas **se
  misturam** no retângulo de interseção — não se ocultam. A ordem no array dá
  z-order, não cor limpa. As opacidades finais saem de verificação visual no
  navegador, não do papel.

## Testes

- `chartOption.test.ts` — `computeOutOfRangeBands` puro: run contíguo acima; run
  abaixo; troca de direção; ponto isolado (largura > 0); quebra por gap; série
  toda dentro (`[]`); sem threshold (`[]`); pontos agregados usando `avg`.
- `chartOption.test.ts` — `buildChartOption`: `markArea.data` contém a faixa
  verde + as faixas X esperadas; faixa de silêncio presente com `now` distante e
  ausente com `now` próximo.
- `KpiWidget.test.tsx` — badge ausente em `fresh`; presente e número atenuado em
  `stale`/`offline`; atenuação vence o `crit` do override.
- `TimeseriesWidget.test.tsx` — badge no header conforme o tier.

Todos com `now` fixo. Suite atual: 421 testes verdes.

## Fora de escopo

- Faixas a partir de `alarm_event` (autoritativas) — decisão consciente acima.
- Envelope min–max desenhado no gráfico para janelas agregadas.
- Tornar `staleMs`/`offlineMs` configuráveis por widget (continuam nos defaults
  de `lib/freshness.ts`).
- `AreaWidget` e `AlarmsWidget` — o pedido cobre KPI e gráfico temporal.
