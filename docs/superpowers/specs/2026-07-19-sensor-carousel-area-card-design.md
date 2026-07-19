# Design: Carrossel de sensores no AreaCard

## Contexto

Hoje `frontend/src/components/AreaCard.tsx` lista todos os sensores de uma área em coluna vertical (`space-y-1`), um `<button>` por sensor com nome + valor em tamanho pequeno (`text-sm`). Objetivo: destacar o valor (maior, mais legível à distância) e, quando a área tem múltiplos sensores, alternar automaticamente entre eles em vez de empilhar todos.

## Decisão de abordagem

Implementação nativa (setInterval + crossfade CSS via Tailwind), sem dependência nova (sem embla/swiper). Motivo: o projeto já usa só `transition-colors duration-200 ease-out` + `motion-reduce:transition-none` como padrão de animação; uma lib de carrossel traria peso e API não usada em nenhuma outra parte do projeto para um requisito simples (trocar 1 valor por vez, sem swipe/gestos).

## Comportamento

### Rotação
- Cada `AreaCard` com **mais de 1 sensor** roda um carrossel interno: mostra 1 sensor por vez, avança pro próximo a cada **3000ms fixo** (hardcoded nesta fase).
- Área com **exatamente 1 sensor**: sem carrossel, sem dots — mostra estático, sempre.
- Ordem de rotação = ordem de `group.sensors` (mesma ordem já usada hoje).

### Pausa
- `onMouseEnter` no card pausa o timer; `onMouseLeave` retoma do zero (não continua de onde parou — reinicia o ciclo de 3s ao sair).
- Sem tratamento especial de touch/mobile nesta fase (dashboard é uso desktop).

### Redução de movimento
- Se `prefers-reduced-motion: reduce`, não faz auto-rotate. Mostra o primeiro sensor (ou o `selectedSensorCode` se houver) fixo. Dots continuam clicáveis manualmente para trocar.

### Indicador (dots)
- Linha de dots abaixo do valor, 1 por sensor (● = ativo, ○ = inativo).
- Dots são clicáveis: clicar pula direto pro sensor correspondente e reinicia o timer de 3s a partir dali.

### Interação com seleção existente
- Clicar no valor/sensor ativo continua chamando `onSelectSensor(s.sensor_code)`, igual ao comportamento atual — não muda a API do componente, só a apresentação interna.

### Visual do valor
- Nome do sensor (`measurement_type.name`) pequeno em cima, como hoje.
- Valor em destaque: fonte maior/bold (`text-3xl font-bold tabular-nums` ou equivalente), unidade ao lado em tamanho menor.
- Cor do valor grande segue `alarm_state` do sensor ativo, usando `statusTextColor(state)` já existente (mesma lógica de cor usada hoje no valor pequeno) — reforça visualmente estados de alerta/crítico mesmo com só 1 sensor visível por vez.
- `StatusDot` do sensor ativo continua visível ao lado do nome, como reforço adicional (dot pequeno colorido + valor grande colorido).

## Estado/lógica

- Estado novo dentro de `AreaCard` (ou hook local `useSensorCarousel`): `activeIndex` (number), avançado por `setInterval(() => setActiveIndex(i => (i + 1) % sensors.length), 3000)`.
- Effect limpa o interval no unmount, na pausa (hover) e ao trocar de índice manual (clique em dot).
- Não precisa de estado global/contexto — cada `AreaCard` tem seu próprio carrossel independente.

## Fora de escopo (fase 1)

- Intervalo configurável via Odoo — vem em fase futura; nesta fase é fixo em 3000ms no código.
- Suporte a swipe/gestos touch.
- Persistir/sincronizar índice ativo entre cards ou entre sessões.

## Testes a cobrir

- Área com 1 sensor: renderiza estático, sem dots.
- Área com N sensores: avança automaticamente a cada 3s (usar fake timers).
- Hover pausa o avanço; mouse leave retoma.
- Clique em dot pula pro sensor certo e reinicia o timer.
- Clique no valor ativo chama `onSelectSensor` com o sensor correto.
- Cor do valor grande reflete `alarm_state` (ok/warn/crit).
- `prefers-reduced-motion`: sem auto-avanço, dots ainda funcionam manualmente.
