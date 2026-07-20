# Design: Indicador de sensor offline / dado velho (A2)

## Contexto

Hoje, quando um sensor não tem valor ao vivo, `frontend/src/components/AreaCard.tsx`
mostra `'—'` (linha 100: `{activeLive ? activeLive.value.toFixed(1) : '—'}`). E
`sensorDisplayState` (em `lib/aggregateStatus.ts`) retorna `'unknown'` ("Sem limite")
tanto quando **não há threshold configurado** quanto quando **não há dado ao vivo**.

O `'—'` e o estado `unknown` colapsam três situações muito diferentes:

1. **Sem limite configurado** — o sensor está vivo e reportando, só falta cadastrar
   `Threshold`. É lacuna de configuração, não de dado.
2. **Dado velho** — o sensor reportou há alguns minutos e parou; o último valor ainda
   está na tela, mas já não é confiável.
3. **Sensor morto / offline** — não chega dado há muito tempo (ou nunca chegou nesta
   sessão).

Num produto médico (CME / RDC 15), o caso (3) é o mais perigoso: **um sensor parado
pode passar por "tudo OK"**. Se a área agrega para verde enquanto um sensor está
silencioso, o operador não tem sinal de que precisa checar o sensor/rede. Esta feature
existe para matar esse "silêncio lido como OK".

### Fatos do código atual (fonte de verdade)

- `LivePoint` (`lib/types.ts`) **já tem** `ts: number` — o timestamp da leitura. A idade
  do dado é `now - live.ts`. Não precisamos de campo novo no `LivePoint` para o caminho
  "ficou velho enquanto eu observava".
- `useLiveStatuses` (`lib/useLiveStatuses.ts`) só atualiza estado **quando chega um novo
  `LivePoint`**. Offline é justamente **ausência de eventos** → o hook nunca re-dispara.
  Para envelhecer o dado precisamos de um relógio próprio que tique (um `now`).
- `AlarmTipoViolacao` (`lib/types.ts`) **já prevê** `'sensor_offline'` e `'erro_leitura'`.
  Ou seja, o backend já modela offline como um tipo de alarme — é a fonte autoritativa
  futura (ver Dependências).
- `worstAlarmState` (`lib/aggregateStatus.ts`) ordena `crit > warn > ok > unknown`. Um
  sensor offline **sem threshold** hoje vira `unknown` = severidade mais baixa =
  invisível na agregação. É exatamente o buraco que esta feature fecha.

### Limitação honesta desta fase (leia antes de prometer)

A detecção client-side por idade do `ts` só pega **"o sensor ficou velho enquanto a
página estava aberta observando"**. Um sensor **já morto no carregamento da página** não
emite nenhum `LivePoint`, logo **não há `ts` contra o qual envelhecer** — e esse é
justamente o caso mais perigoso num monitor. Portanto:

> **A fase 1 sozinha NÃO fecha completamente o gap.** Ela cobre a degradação observada em
> tempo real e sinaliza "sem dado desde a carga" após uma janela de graça. O fechamento
> completo depende do backend expor um `last_seen_ts` autoritativo por sensor (ver
> Dependências). A spec deixa isso explícito de propósito para não prometer demais.

## Decisão de abordagem

**Freshness (frescor do dado) é um eixo separado do `alarm_state`.** Não vamos misturar
"idade do dado" dentro de `computeStatus` / `alarm_state` (que descrevem se o *valor*
está dentro do limite). Em vez disso:

1. Uma função pura nova `freshness(live, now, cfg)` em `lib/freshness.ts` que classifica a
   idade do último dado em tiers: `fresh` | `stale` | `offline` | `never`.
2. Um hook de relógio compartilhado `useNow(intervalMs)` que devolve `Date.now()`
   atualizado periodicamente, para forçar re-render e reavaliar a idade mesmo sem eventos
   novos. **Um único `setInterval` compartilhado** (padrão de multiplexação já usado no
   `real/liveApi.ts`), não um timer por card.
3. O `AreaCard` combina `alarm_state` (valor) + `freshness` (dado) na apresentação e na
   agregação da área.

Motivo de manter separado: as ações do operador são diferentes. `warn`/`crit` = "observe
o valor". `offline`/`stale` = "cheque o sensor / a rede". Colapsar os dois eixos num só
estado esconderia essa distinção.

## Comportamento

### Tiers de frescor e thresholds

`freshness(live, now, cfg)` computa `ageMs = now - live.ts` e classifica:

| Tier      | Condição (defaults)        | Significado                                  |
|-----------|----------------------------|----------------------------------------------|
| `fresh`   | `ageMs ≤ 5 min`            | Dado confiável. Sem badge (comportamento atual). |
| `stale`   | `5 min < ageMs ≤ 15 min`   | "Velho": valor ainda visível, mas suspeito.  |
| `offline` | `ageMs > 15 min`           | Sensor tratado como parado.                  |
| `never`   | nenhum `LivePoint` recebido| Sem dado nesta sessão (o antigo `'—'`).      |

- **Defaults propostos: `staleMs = 5 min`, `offlineMs = 15 min`.** São palpites razoáveis
  para esta fase, **hardcoded** em `lib/freshness.ts`.
- **Configuráveis em fase futura** (via `DashboardConfig`, ao lado de
  `carousel_interval_ms`). Ver Fora de escopo / Dependências.
- **Ressalva importante:** esses defaults só fazem sentido se a **cadência esperada de
  reporte** for muito menor que o threshold de "velho". Um sensor que legitimamente
  reporta a cada 10 min dispararia falso-positivo de `stale`/`offline`. Quando os
  thresholds forem configuráveis, o ideal é derivá-los do intervalo de amostragem
  esperado por sensor. Registrar como limitação conhecida.

### O relógio `now` (`useNow`)

- Hook `useNow(intervalMs = 30_000)` em `lib/useNow.ts`: mantém `Date.now()` num state e
  atualiza a cada `intervalMs` via um **interval compartilhado** entre todos os
  assinantes (contagem de referência), não um timer por componente.
- Granularidade de 30s é suficiente: a idade é exibida em minutos, e o cruzamento
  `fresh→stale→offline` está na escala de minutos.
- Reavaliar a idade a cada tick faz `stale`/`offline` aparecerem **sem** um novo evento —
  é o núcleo da feature.
- (Opcional, fora do caminho crítico) pausar o tick quando a aba está oculta
  (`visibilitychange`) para poupar CPU; não é requisito de fase 1.

### Visual

Três tratamentos **visualmente distintos**, para nunca confundir "sem limite" com
"offline":

1. **`fresh`** — exatamente como hoje. Valor grande, cor por `alarm_state`
   (`statusTextColor`), `StatusDot`. Sem badge de idade.

2. **`stale` (velho)** — o valor continua visível (é o último conhecido) porém **atenuado**
   (ex.: opacidade reduzida), e ganha um **badge de idade** ao lado do nome do sensor:
   ícone de relógio + texto `"há 6 min"`, em tom de atenção (`--color-warn`). Comunica
   "isto ainda está na tela mas já não é fresco".

3. **`offline`** — badge dominante com ícone de **desconexão** (ex.: sensor/wifi cortado)
   + `"há 17 min"` ou `"offline"`, em `--color-crit`. O valor grande é **fortemente
   atenuado** (ou substituído por `'—'`), porque não deve mais ser lido como leitura
   atual. `StatusDot` do sensor reflete o estado offline (cor crit/distinta), não o
   `alarm_state` antigo.

4. **`never`** — mantém `'—'`, mas com rótulo neutro **"aguardando dado"** (não
   "offline"): na carga ainda não sabemos se o sensor está morto ou só demorando o
   primeiro ponto. Depois de uma **janela de graça** (proposta: `2 × staleMs`) sem
   nenhum ponto, escalar visualmente para o tratamento `offline` — mas essa escalada é o
   ponto fraco desta fase (ver limitação acima) e só fica robusta com `last_seen_ts` do
   backend.

**Distinção de "Sem limite" (`unknown`):** permanece inalterada — ícone de círculo
tracejado (`StatusIcon` `unknown`), cor `--color-muted`, valor normal e presente. "Sem
limite" descreve *configuração*; freshness descreve *dado*. Um mesmo sensor pode estar
"sem limite" **e** "fresh" (vivo, só sem threshold) — nesse caso mostra valor normal +
ícone unknown, **sem** badge de idade.

Formatação da idade: helper `formatAge(ageMs)` → `"há 6 min"`, `"há 1 h 20 min"`, etc.
(pt-BR, granularidade em minutos; segundos só abaixo de 1 min, mas abaixo de 1 min é
`fresh` e não mostra badge — então na prática sempre minutos+).

### Interação com `alarm_state` e agregação da área

Regra central (é o motivo de ser da feature):

> **Frescor é eixo separado, mas offline SEMPRE escala a área para no mínimo `warn`,
> independentemente do `alarm_state`/`unknown` daquele sensor.**

Concretamente, ao computar o estado agregado da área em `AreaCard`:

- Para cada sensor, calcula-se `displayState` (como hoje) **e** `freshness`.
- Sensor com `freshness === 'offline'` (ou `never` após a janela de graça) **força** a
  contribuição desse sensor para a agregação a ser **no mínimo `warn`** — mesmo que seu
  `displayState` seja `ok` ou `unknown`. Isso impede o caso fatal: sensor offline sem
  threshold contribuindo `unknown` (severidade mais baixa) e a área brilhando verde.
- `freshness === 'stale'`: **não** altera a agregação da área nesta fase (só o badge no
  nível do sensor), para evitar ruído. Decisão revisável; deixar configurável junto dos
  thresholds.
- A política "offline → warn" (em vez de `crit`) é o default conservador de fase 1;
  escalar offline para `crit` é uma opção configurável futura.

**Marcador distinto no nível da área:** mesmo quando a severidade agregada é `warn`, a
área deve indicar que o motivo é *offline*, não valor-perto-do-limite — porque a ação do
operador difere. Proposta: além do `StatusChip`/borda em `warn`, exibir um pequeno
marcador de offline no cabeçalho da área (ícone de desconexão), análogo ao selo `!` de
`hadAlarmToday` já existente. Assim `warn-por-valor` e `warn-por-offline` são
distinguíveis num relance.

### Onde fica a lógica

- `lib/freshness.ts` — puro: `freshness(live, now, cfg)`, `formatAge(ageMs)`, constantes
  de threshold. Sem React, 100% testável.
- `lib/useNow.ts` — hook do relógio compartilhado.
- `components/AreaCard.tsx` — consome `useNow`, chama `freshness` por sensor, aplica o
  visual e a escalada de agregação. O badge/ícone pode virar um componente pequeno
  (`FreshnessBadge`) reusando o padrão de `StatusDot`/`statusVisuals`.
- Ajuste na agregação: encapsular a regra "offline escala para ≥ warn" numa função pura
  (ex.: `areaAggregateState(perSensor: {display, freshness}[])`) para testar isolado, em
  vez de espalhar `if` no JSX.

## Fora de escopo (fase 1)

- **`last_seen_ts` autoritativo do backend** — o que fecha de verdade o caso "morto no
  load". Fica como dependência/pré-requisito, não implementação desta fase.
- **Consumir o alarme `sensor_offline`/`erro_leitura` do backend** como fonte autoritativa
  de offline (em vez de inferir por idade no cliente).
- **Thresholds configuráveis** (`staleMs`/`offlineMs`) via `DashboardConfig` e por sensor.
  Nesta fase são fixos no código.
- **Escalar offline para `crit`** (fica em `warn`) e **`stale` afetar agregação**.
- Derivar thresholds da cadência de amostragem esperada por sensor.
- Notificação/som/histórico de eventos de offline; badge de "offline hoje" análogo a
  `hadAlarmToday`.
- Pausar o tick em aba oculta (otimização, não requisito).

## Testes a cobrir

Função pura `freshness` (com `now` injetado — nada de `Date.now()` real nos testes):

- `ageMs` dentro de `staleMs` → `fresh`.
- `staleMs < ageMs ≤ offlineMs` → `stale`.
- `ageMs > offlineMs` → `offline`.
- `live === undefined` → `never`.
- Fronteiras exatas (`= staleMs`, `= offlineMs`) classificadas de forma determinística.
- `formatAge`: 90s → "há 1 min"; 6 min; > 1h com horas+min; pt-BR.

Agregação (`areaAggregateState`, o **guarda de regressão da razão de ser da feature**):

- **Sensor offline SEM threshold (displayState `unknown`) → a área NÃO mostra `ok`;
  agrega para ≥ `warn`.** (teste crítico)
- Sensor offline com `displayState 'ok'` → área ≥ `warn`.
- Sensor `crit` + outro offline → área permanece `crit` (offline não rebaixa).
- Todos `fresh` e `ok` → área `ok` (offline não gera falso-positivo).
- `stale` **não** altera a agregação da área (só badge de sensor).

`AreaCard` (React, com `now` controlado / fake timers):

- `fresh`: valor normal, sem badge de idade.
- `stale`: valor atenuado + badge "há N min" em tom de atenção.
- `offline`: badge de desconexão + valor atenuado/`—`; `StatusDot` reflete offline.
- `never`: rótulo "aguardando dado"; após janela de graça, escala para offline.
- "Sem limite" + `fresh` (vivo, sem threshold): valor normal + ícone unknown, **sem**
  badge de idade — não confundir com offline.
- Cabeçalho da área mostra marcador distinto de offline quando a agregação virou `warn`
  por offline (distinguível de warn-por-valor).
- Avançar o relógio `now` faz um sensor cruzar `fresh → stale → offline` **sem** nenhum
  `LivePoint` novo (fake timers) — prova que o tick, e não o evento, envelhece o dado.

`useNow`:

- Emite valores crescentes de tempo no intervalo; um único interval compartilhado entre
  múltiplos assinantes; limpa no unmount do último.

## Dependências / pré-requisitos

1. **Timestamp de relógio real no mock (PRÉ-REQUISITO / bloqueia a demo).**
   `lib/api/mock/liveApi.ts` emite `ts` **sintético**: começa em
   `1_700_000_000_000` (14/nov/2023) e soma 1s por tick. Com o relógio atual (2026),
   `now - ts` dá **anos** → no mock **todo sensor apareceria offline** e a demo/visual
   quebra. O mock precisa emitir `ts` de **relógio real** (`Date.now()`-based). É a mesma
   classe de armadilha já registrada no MEMORY ("mock escondeu render vazio" no ECharts):
   verificar sempre o mock contra a lógica nova.

2. **Unidade do `ts` — confirmar contrato (SUPOSIÇÃO A VERIFICAR).** O mock usa
   **milissegundos** (13 dígitos). O `real/liveApi.ts` (linha 32) apenas repassa o campo
   `time` cru do backend para `ts`, **sem normalizar**. Se o backend enviar epoch em
   **segundos**, `Date.now() - ts` erra por **1000×** e toda a classificação de frescor
   fica errada. Confirmar que o backend envia ms (ou normalizar na borda em
   `real/liveApi.ts`).

3. **`last_seen_ts` autoritativo do backend (fecha o gap de verdade).** Para detectar
   sensor **morto antes do page-load** — o caso mais perigoso — o frontend precisa de um
   "última vez visto" vindo do servidor no snapshot/meta do sensor (ex.: em `getSensor` /
   `listSensors` de `MetaApi`, ou num endpoint de status). Idealmente o backend também
   expõe uma **flag/alarme autoritativo de offline** (o `sensor_offline` já modelado em
   `AlarmTipoViolacao`), e o frontend passa a **preferir** essa fonte à inferência por
   idade. Sem isso, a fase 1 só cobre a degradação observada em tempo real.

4. **`DashboardConfig` para thresholds configuráveis (fase futura).** Estender
   `DashboardConfig` (`lib/types.ts`) com `stale_ms` / `offline_ms` (globais e/ou por
   sensor), servidos pelo `ConfigApi.getConfig`, para remover os defaults hardcoded.
