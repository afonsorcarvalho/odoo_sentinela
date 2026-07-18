# Design — Frontend Sentinela CME: tela Overview (visão do cliente)

> Spec de implementação. Complementa `frontend_spec.md` §8.1 e o slice anterior
> (`docs/superpowers/specs/2026-07-18-frontend-sensor-detail-design.md`, cuja
> direção visual "instrumento calibrado" e seam mock→real são reusadas aqui
> sem alteração). Segunda fatia da Fase 4 do `roadmap_implementacao.md`,
> construída contra mocks.

## 1. Objetivo e escopo

Tela **Overview** — visão do cliente: cartões por área do site, cada um
mostrando o estado atual agregado (verde/alarme, com a mesma linguagem de
cor+ícone+texto do slice anterior) e a contagem de alarmes ativos.

**Escopo desta fatia:**
- Só visão do cliente (1 site). Visão consolidada multi-cliente do operador
  SaaS fica fora — fatia futura.
- Sem navegação: clicar num cartão **não** leva ao Detalhe do Sensor. Sem
  roteamento nesta fatia.
- **Overview vira a tela raiz** (`App.tsx`). `SensorDetailPage` continua
  existindo, testada e funcional, mas fica temporariamente inalcançável pela
  UI — roteamento real conectando as duas telas é trabalho de uma fatia
  futura (ver `frontend_spec.md` §8, telas 1→2).

## 2. Dados mock — de 1 sensor para N

Hoje o mock só conhece um sensor fixo (`TEMP-EXP-01`). Esta fatia expande
para 3 sensores (1 por área), com thresholds reais de
`odoo_modelo_dados_spec.md` §7:

| Área | Sensor | Threshold |
|---|---|---|
| Expurgo | `TEMP-EXP-01` (já existe) | 18–22°C, padrão regulatório |
| Preparo/Esterilização | `TEMP-PRE-01` (novo) | 20–24°C, padrão regulatório |
| Arsenal | `TEMP-ARS-01` (novo) | **sem threshold** (spec não define um padrão regulatório para Arsenal) |

O sensor do Arsenal sem threshold é deliberado: exercita o estado "sem
limite" já coberto pelo `ThresholdBadge` (slice anterior), sem inventar um
valor não documentado na spec.

### 2.1 `MetaApi` ganha `listSensors()`

```ts
export type MetaApi = {
  getSensor(code: string): Promise<SensorMeta>
  getThreshold(code: string): Promise<Threshold | null>
  listSensors(): Promise<SensorMeta[]>   // novo
}
```

`getSensor`/`getThreshold` hoje **ignoram** o parâmetro `code` (sempre
devolvem a fixture única). Esta fatia corrige isso: passam a buscar pelo
`code` de verdade nas novas fixtures (comportamento observável para
`TEMP-EXP-01` não muda — só passa a funcionar corretamente para os outros
códigos).

### 2.2 `liveApi` por sensor

`liveApi.subscribe(code, cb)` hoje ignora `code` para efeitos de threshold
(sempre usa a fixture única `THRESHOLD`, mesmo ponto médio/amplitude). Passa
a resolver o threshold e o ponto médio da onda sintética pelo `code`
recebido, para que sensores diferentes mostrem comportamento diferente na
demo (ex.: um oscilando dentro da faixa, outro cruzando para fora
ocasionalmente) — mesma técnica de geração senoidal já usada, só
parametrizada por sensor em vez de fixa.

## 3. Agregação por área

Nova função pura `worstAlarmState(states: AlarmState[]): AlarmState`
(`src/lib/aggregateStatus.ts`) — dado os estados de todos os sensores de uma
área, devolve o pior (`crit` > `warn` > `ok`). Com 1 sensor por área nesta
fatia o resultado é trivial (= o estado daquele sensor), mas a função já
serve para quando site→área (fatia futura) tiver múltiplos sensores por
área — evita reescrever a agregação depois.

**Contagem de "alarme ativo"** por área = número de sensores da área
atualmente em `crit`. Não conta `warn`: alinhado ao modelo real
(`sensor_monitor.alarm.event` só nasce de violação de limite — que é
`crit`/fora da faixa —, não de "perto do limite").

## 4. Novo hook: `useLiveStatuses`

```ts
function useLiveStatuses(codes: string[]): Record<string, LivePoint>
```

Assina `liveApi.subscribe` para cada código em `codes`, mantém um mapa
`sensor_code → último LivePoint` em estado local, desinscreve tudo no
unmount / quando `codes` muda. **Não** usa `useLiveTail` (que guarda um
buffer de até 300 pontos por sensor — over-kill aqui; Overview só precisa do
valor/estado atual de cada sensor, não do histórico da cauda).

## 5. Componentes

```
OverviewPage
└── AreaCard × N   — nome da área, categoria, status agregado
                      (cor + ícone + texto — mesmo vocabulário de
                      LiveReadout/status.ts), badge de contagem de alarmes
                      crit (só aparece quando count > 0)
```

- `AreaCard` recebe `{ area: {area_code, name, category}, sensors: SensorMeta[], liveByCode: Record<string, LivePoint> }`
  — deriva o `AlarmState` de cada sensor (via `state` do `LivePoint` já
  presente no feed, igual ao `LiveReadout` já faz) e agrega com
  `worstAlarmState`.
- Nenhum elemento visual novo: reusa `LABELS`/cores exportadas de
  `status.ts` (ok/warn/crit/unknown → ícone+cor+texto), grid responsivo
  (`repeat(auto-fit, minmax(...))`, mesma convenção de layout estrutural do
  slice anterior).
- `OverviewPage`: busca `useSensors()` (novo hook em `lib/queries.ts`,
  `useQuery` sobre `metaApi.listSensors()`), agrupa por `area.area_code`,
  assina `useLiveStatuses` com todos os `sensor_code`, renderiza um
  `AreaCard` por área.

## 6. Fluxo de dados

```
metaApi.listSensors() ─ TanStack Query (useSensors) ─→ agrupamento por área (client-side)
liveApi.subscribe(code) × N ─ useLiveStatuses ─→ estado atual por sensor ─→ worstAlarmState por área
```

## 7. Estados de erro/loading

- Loading: skeleton por cartão (mesma convenção do slice anterior — não
  spinner global).
- Erro em `listSensors`: mensagem no lugar da grade, com retry (reusa o
  padrão já usado no painel de histórico do slice anterior).

## 8. Testes

1. `worstAlarmState`: pura, casos ok/warn/crit/misto/vazio.
2. `MetaApi.listSensors` mock: devolve os 3 sensores; `getSensor`/`getThreshold`
   agora respeitam o `code` recebido (inclusive Arsenal → threshold `null`).
3. `useLiveStatuses`: acumula último ponto por código, desinscreve todos no
   unmount (mesmo padrão não-tautológico do `useLiveTail` — spy nos
   unsubscribes).
4. `AreaCard`: status agregado correto (cor+ícone+texto, nunca só cor),
   badge de contagem só aparece com `crit > 0`, Arsenal mostra "sem limite"
   sem quebrar a agregação.
5. `OverviewPage`: renderiza 3 cartões agrupados corretamente; smoke de
   integração com os mocks reais (não fakes) — mesmo padrão do
   `SensorDetailPage.test.tsx`.

## 9. Entregáveis desta fatia

- Fixtures expandidas (3 sensores/thresholds) + `MetaApi.listSensors`.
- `liveApi` parametrizado por sensor.
- `lib/aggregateStatus.ts` (`worstAlarmState`).
- `lib/useLiveStatuses.ts`.
- `components/AreaCard.tsx`.
- `pages/OverviewPage.tsx`.
- `App.tsx` passa a renderizar `OverviewPage`.
- Suite de testes verde; **verificação visual real** (playwright+chromium,
  como no slice anterior — o slice anterior provou que testes com libs
  mockadas escondem bugs de render).

## 10. Fora desta fatia (próximas)

Roteamento conectando Overview → Site→Área → Detalhe do Sensor; visão
operador SaaS multi-cliente; múltiplos sensores por área (pressão
diferencial além de temperatura); painel de alarmes com ciclo de vida.
