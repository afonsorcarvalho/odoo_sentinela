# Design: Config persistida por widget via UI (B2)

**Data:** 2026-07-19
**Status:** Aprovado (brainstorm)
**Depende de:** dashboard customizável (`2026-07-19-dashboard-customizavel-design.md`) e config no Odoo (`2026-07-19-dashboard-config-odoo-design.md`) — ambos concluídos e mergeados.

## Contexto

O dashboard customizável já existe: grid drag/resize, layout salvo como blob JSON no Odoo
(`PUT /config/layout`), validado no frontend por zod (`lib/layout/schema.ts`). Cada widget é
uma `WidgetInstance` com `binding` (área/sensor) e `options` (um saco de configuração por
tipo). Hoje o `WidgetConfigPopover` (só montado em modo edição, dentro do `WidgetFrame`)
edita **apenas o binding** — a `options` de cada widget usa **defaults fixos** e não há UI
para mudá-la. Objetivo desta melhoria (B2): permitir configurar, **pela UI e por widget**, e
persistir três coisas concretas:

1. **Janela default** do gráfico no `TimeseriesWidget` (`defaultWindow`).
2. **Threshold** do `KpiWidget` (limites que definem a cor de estado do valor).
3. **Escopo** do alarme no `AlarmsWidget` (`scope` site/área).

## Descoberta que orienta a abordagem

A persistência **já está pronta**. O campo `options` já existe no `widgetInstanceSchema`
(`z.record(z.string(), z.unknown()).optional().default({})`), o registry já **consome**
`w.options?.defaultWindow`, `w.options?.scope`, `w.options?.label`, e o `options` já
**round-trips** no blob salvo via `useSaveLayout` → `PUT /config/layout`. Ou seja: se o
popover escrever em `widget.options` e chamar `onChange`, o valor **já persiste** sem tocar
backend, API, contratos ou queries.

A lacuna real de B2 é portanto só de **frontend**:
- (a) **tipar** `options` por tipo de widget (hoje é `unknown`, lido com casts frouxos);
- (b) dar **UI** de config por tipo no popover (só edição);
- (c) **fiar** o threshold no `KpiWidget`, que hoje colore só pelo `alarm_state` ao vivo e
  não lê nenhuma option de threshold.

## Decisão de abordagem

### 1. Reusar o campo `options` (não criar `config` novo)

Manter a **chave `options`** como o local da "config por widget". Não renomear para `config`.
Motivo: `options` já existe, já é consumido pelo registry e já persiste em blobs salvos em
produção (com `defaultWindow`/`scope`/`label`). Renomear exigiria uma migração
`options`→`config` de blobs antigos para **zero ganho funcional**. "Config por widget" é o
**conceito**; `options` é a **chave** que o encarna. (Nas próximas seções, "config" e
"options" referem-se à mesma coisa.)

### 2. Tipar `options` por tipo, via schema no descriptor do registry

O design original do dashboard customizável (§4) já previa `optionsSchema?: ZodSchema` no
`WidgetDescriptor`. B2 concretiza isso: cada descriptor ganha um **`optionsSchema` zod com
defaults**, e o `parseLayout` valida/coage a `options` de cada widget com o schema do seu
`type`. Preferido a uma `z.discriminatedUnion('type', …)` no `WidgetInstance` inteiro porque
esta arrastaria também `binding` para a união (refactor maior) sem benefício — a validação
por tipo da `options` é o que precisamos, e um mapa `type → schema` é local e testável.

Defaults no próprio schema (`.default(...)`) resolvem a **backward-compat** de graça: blob
antigo sem a option cai no default; blob sem `options` nenhum idem (ver §Migração).

### 3. UI no popover existente (só edição)

Estender o `WidgetConfigPopover` — não criar componente novo. Ele já é montado **só em modo
edição** (o `WidgetFrame` só o renderiza sob `editing && open`), então a config fica
naturalmente restrita ao admin editando. O popover passa a ter duas seções: **Binding** (o
que já faz) e **Config** (campos por tipo, novo). Operador em modo view nunca vê o popover.

## Schema — extensão

`lib/layout/schema.ts`. O `widgetInstanceSchema` deixa de ter `options` genérico; a `options`
passa a ser validada pelo schema do tipo. Forma pretendida (pseudo-zod):

```ts
// options por tipo — `.catch(default)` por campo cobre tanto AUSENTE (backward-compat)
// quanto INVÁLIDO (blob editado à mão) sem lançar — degrada campo a campo.
const timeseriesOptions = z.object({
  defaultWindow: z.enum(['1h', '24h', '7d', '30d']).catch('24h'),
})
const kpiOptions = z.object({
  label: z.string().optional().catch(undefined),
  limiteMin: z.number().optional().catch(undefined),  // override display-only (§KPI)
  limiteMax: z.number().optional().catch(undefined),  // NUNCA suaviza alarm_state
}).refine((o) =>
  o.limiteMin == null || o.limiteMax == null || o.limiteMin <= o.limiteMax,
  { message: 'limiteMin deve ser ≤ limiteMax' })
const alarmsOptions = z.object({
  scope: z.enum(['site', 'area']).catch('site'),
  // areaCode do escopo mora no binding.areaCode (já existe), não aqui
})
const areaOptions = z.object({})  // sem config em B2; strip descarta chaves desconhecidas

export const OPTIONS_SCHEMA = {
  timeseries: timeseriesOptions,
  kpi: kpiOptions,
  alarms: alarmsOptions,
  area: areaOptions,
} satisfies Record<WidgetType, z.ZodTypeAny>

// Parse de options que NUNCA lança: option-set inválido (incl. refine do kpi falhando,
// ex. limiteMin>limiteMax num blob editado à mão) cai nos defaults daquele tipo.
function parseOptions(type: WidgetType, raw: unknown) {
  const schema = OPTIONS_SCHEMA[type]
  const r = schema.safeParse(raw ?? {})
  return r.success ? r.data : schema.parse({})  // schema.parse({}) é seguro: só defaults, refine passa
}
```

**Mecanismo (explícito):** `options` e `type` são irmãos no `widgetInstanceSchema`, então um
`z.object` puro não faz `options` depender de `type`. Duas opções — a spec escolhe (a):

- **(a) escolhida — `.transform` no `widgetInstanceSchema`:** após validar a forma base
  (`options` como `z.record(z.string(), z.unknown()).optional().default({})`, como hoje), um
  `.transform((w) => ({ ...w, options: parseOptions(w.type, w.options) as Record<string, unknown> }))`
  reescreve `options` **em runtime** com defaults/coerção do schema do tipo. Fica dentro do
  único `safeParse` de `parseLayout` (o `parseLayout` **não** muda de assinatura nem ganha 2º
  passe manual).
- (b) rejeitada — 2º passe mapeando `widgets` fora do schema: espalha a validação em dois
  lugares.

**Tipagem (decisão crítica p/ isolar as tasks — o tipo ESTÁTICO de `options` NÃO muda):** o
cast `as Record<string, unknown>` no transform é **intencional** — mantém o tipo estático de
`WidgetInstance.options` idêntico ao de hoje (`Record<string, unknown>`). Motivo: estreitar o
tipo (união dos shapes, ou `discriminatedUnion`) quebraria o `tsc` de **todos** os consumidores
atuais de graça (`registry.tsx` faz `w.options?.defaultWindow as Window`; `WidgetConfigPopover`,
`newWidget`, `DashboardEditor` idem) — um ripple que sai do escopo de T1 (schema puro). O ganho
de B2 é **validação + defaults em runtime**, não tipagem estática mais forte: depois do
transform o valor em runtime está garantidamente válido/coagido, então os casts existentes do
registry (`as Window` etc.) passam a ser **casts sobre dado já validado** (seguros), sem
precisar mudar linha nenhuma neles. Tipagem correlacionada real (`z.discriminatedUnion('type',
…)`, casts zero) fica como opção futura — fora de escopo aqui.

**Robustez:** dois níveis, ambos sem derrubar o layout: (1) **por campo** — `.catch(default)`
em cada campo faz valor inválido cair no default do campo; (2) **por option-set** — o
`parseOptions` acima usa `safeParse` com fallback aos defaults do tipo, cobrindo a falha do
`refine` object-level do kpi (que é erro de validação, capturado por `safeParse`, **não** uma
exceção que suba). O `parseLayout` continua retornando `null` só se a **forma base** do layout
for irrecuperável (como hoje) — nunca por causa de uma option ruim.

## Os três casos concretos

### Timeseries — `defaultWindow`

- **Campo:** `defaultWindow: '1h' | '24h' | '7d' | '30d'`.
- **Default:** `'24h'` (igual ao default atual do `TimeseriesWidget`).
- **Validação:** enum (zod já garante). Sem valor livre.
- **UI:** reusar o `WindowSelector` dentro do popover (mesmo grupo de chips 1h/24h/7d/30d).
  `value={widget.options.defaultWindow}`, `onChange` grava em `options.defaultWindow`.
- **Fluxo já existente:** o registry já passa `defaultWindow={w.options?.defaultWindow}` para
  o `TimeseriesWidget`, que o usa como estado inicial da janela (`useState(defaultWindow)`).
  Nada muda no widget. Nota: mudar o default **não** re-força a janela de uma instância já
  aberta pelo operador — é o *default* de abertura, coerente com o nome.

### KPI — threshold

Hoje o `KpiWidget` colore o valor só pelo `last.alarm_state` (ok/warn/crit vindo do live).
B2 adiciona um **override de threshold por widget**: campos opcionais `limiteMin`/`limiteMax`.

- **Campos:** `limiteMin?: number`, `limiteMax?: number`, e o `label?` já existente.
- **Defaults:** ambos `undefined`. Quando ausentes, o widget colore **só** pelo
  `last.alarm_state` do backend — exatamente o comportamento atual (nada visualmente muda para
  KPIs já salvos; não introduz `useThreshold` nem query nova).
- **Semântica de cor (CRÍTICA — o override NUNCA suaviza o alarme real):** o override é
  **display-only** e só pode **escalar** a severidade, nunca rebaixá-la. O `alarm_state`
  autoritativo do backend (`last.alarm_state`) continua sendo o piso da cor. O widget:
  1. parte do `alarm_state` ao vivo (ok/warn/crit/unknown), como hoje;
  2. se há override e o valor ao vivo (`last.value`) está **fora** de `[limiteMin, limiteMax]`,
     eleva o estado para `crit`;
  3. cor final = `max(estado_backend, estado_override)` na ordem `unknown < ok < warn < crit`.

  Ou seja: um KPI cujo backend disparou `crit` (por taxa de variação, alarme externo, etc.)
  **jamais** aparece verde por estar "dentro" do limite local — o override só adiciona
  alarme, nunca esconde. Isto evita a mesma classe de bug da A2 ("silêncio/valor-ok lido como
  OK" enquanto o sensor está de fato em alarme). Convenção de cor inalterada
  (ok/unknown = `--color-ink`; warn/crit = token de estado). Sem `last` (sem leitura) →
  `unknown`, valor `—`, como hoje. O tier `warn` é preservado porque vem do backend; o
  override local só introduz `crit` (fora de faixa), não um `warn` intermediário nesta fase.
- **Validação:** ambos numéricos; se ambos preenchidos, `limiteMin ≤ limiteMax` (refine no
  schema, ver acima); cada um sozinho é válido (só piso ou só teto).
- **UI:** dois inputs `number` ("Limite mín." / "Limite máx.") + o input de `label` (texto).
  Placeholder mostra o valor herdado do sensor quando o campo está vazio, deixando claro que
  vazio = "usar cadastro do sensor".
- **Feedback inline (min>max):** quando ambos preenchidos e `limiteMin > limiteMax`, o popover
  mostra uma mensagem de erro inline abaixo dos campos (usa a validação do `kpiOptions.refine`
  / mesma checagem). Não bloqueia o "Salvar" global (o popover não tem Salvar próprio — ver
  §Testes), mas dá ao admin o feedback que evita a perda silenciosa: sem o aviso, um blob
  min>max salvo seria coagido aos defaults no reload sem o admin perceber. A cor (`--color-*`)
  do erro segue os tokens de estado do projeto (`crit`).
- **Fiação nova (única mudança de widget):** `KpiWidget` passa a receber `limiteMin`/
  `limiteMax` (via registry, de `w.options`). Quando ao menos um está setado, computa o
  `estado_override` (fora de faixa → `crit`) e usa `max(last.alarm_state, estado_override)`
  para a cor. Sem override, comportamento idêntico ao atual (só `last.alarm_state`). **Nota:**
  o override é auto-suficiente (compara `last.value` com os limites do próprio widget) — não
  precisa de `useThreshold`, então não adiciona query nova (evita alimentar o N+1 do E1). O
  fallback ao threshold cadastrado do sensor fica **fora de escopo** desta fase; sem override,
  a cor segue exclusivamente o `alarm_state` do backend, como hoje.

### Alarms — `scope`

- **Campo:** `scope: 'site' | 'area'`. Quando `'area'`, o `areaCode` do filtro mora no
  `binding.areaCode` (já existente e já consumido pelo registry/`AlarmsWidget`).
- **Default:** `'site'` (igual ao `newWidget`/`defaultLayout` atuais).
- **Validação:** enum. Regra de coerência: `scope === 'area'` **exige** `binding.areaCode`;
  sem ele o widget renderiza o painel de site (fallback seguro do `AlarmsWidget` atual, que
  só filtra `if scope==='area' && areaCode`) — não bloqueia salvar, alinhado à decisão §8 do
  design do dashboard (permitir salvar + degradar visual em vez de travar).
- **UI (nova no popover):** um select "Escopo" (Site / Área). Ao escolher "Área", revela o
  select de área (o mesmo dropdown de áreas que o popover já sabe montar para `needs==='area'`)
  gravando em `binding.areaCode`. Isto é config para um `type` cujo `needs === 'none'`, então
  o popover deixa de decidir a UI só por `needs`: passa a compor **binding-por-`needs`** +
  **config-por-`type`** (ver §UI abaixo).

## UI — extensão do WidgetConfigPopover

O popover passa a renderizar, além da seção de binding atual (dirigida por `descriptor.needs`),
uma seção de **Config** dirigida por `widget.type`:

```
[Header: label do tipo]
── Binding ──   (como hoje: área p/ needs==='area', sensor p/ needs==='sensor')
── Config ──    (novo, por type)
   timeseries → WindowSelector (defaultWindow)
   kpi        → label + limiteMin + limiteMax
   alarms     → scope (site/área) + [select de área se 'area']
   area       → (nada em B2)
[Fechar]
```

- Todas as edições fluem pelo `onChange(next)` já existente (`WidgetFrame` → `DashboardEditor`
  → cópia local do layout). Nenhuma escrita direta no servidor no popover.
- Manter o estilo/tokens atuais do popover (`--color-surface`, `--color-muted`, `text-xs`).
- A11y: cada campo com `<label>`; o select de área do escopo só existe no DOM quando
  `scope==='area'`.

## Fluxo config → widget (props)

Inalterado em forma, só passa a carregar mais campos: `blob → parseLayout (valida options por
tipo) → DashboardGrid → WidgetFrame → registry[type].render(widget) → props do componente`.
O registry é o **único** ponto que traduz `w.options.*` em props; os widgets recebem props
tipadas (`defaultWindow`, `scope`/`areaCode`, `label`/`limiteMin`/`limiteMax`) e não conhecem
o schema. Único widget com prop nova: `KpiWidget` (`limiteMin`/`limiteMax`).

## Migração / backward-compat

- **Blob sem `options`** (ou `options: {}`): `OPTIONS_SCHEMA[type].parse({})` preenche os
  defaults do tipo → comportamento idêntico ao atual.
- **Blob com `options` parcial** (ex.: `{ scope: 'site' }` de hoje): campos ausentes caem no
  default; presentes são validados.
- **Option inválida** (tipo errado por edição manual do blob): cai no default do campo, não
  derruba o layout (o `parseLayout` continua nunca quebrando a tela do operador — cai no
  `defaultLayout` só se o layout como um todo for irrecuperável).
- **`version` do layout continua `1`.** A mudança é aditiva e retrocompatível (defaults
  cobrem tudo), então **não** incrementa a versão nem exige passo em `migrate()`. Se numa
  fase futura uma option mudar de forma de modo incompatível, aí sim `version: 2` + `migrate`.

## Persistência

Nenhuma mudança de backend/API/contratos. A `options` já viaja no blob:
`useSaveLayout()` → `configApi.saveLayout(layout)` → `PUT /config/layout` → `layout_json` no
Odoo. "Salvar" persiste as options junto; "Cancelar" descarta a cópia local (comportamento do
`DashboardEditor` atual). O gate de admin do endpoint (`exigir_admin`) já protege a escrita.

## Escopo — fase 1 (enxuto)

- Só **três** tipos ganham config: `timeseries` (defaultWindow), `kpi` (threshold + label),
  `alarms` (scope). `area` **não** ganha config nesta fase.
- Só os campos listados acima. Sem opções cosméticas extra.
- Reuso máximo: `options` existente, `WindowSelector` existente, dropdown de área existente,
  persistência existente.

## Fora de escopo

- Config para **todo** tipo de widget (ex.: `area` — intervalo de carrossel por widget; o
  intervalo hoje é por site, ver `dashboard-config-odoo-design.md`).
- Novos campos de config além dos três casos (título custom do timeseries, cor custom do KPI,
  filtros avançados de alarme, etc.).
- Migração `options`→`config` (mantemos a chave `options`).
- `version: 2` do schema / passo em `migrate()` (mudança é aditiva/retrocompatível).
- Escrever threshold do KPI **de volta** no cadastro do sensor no Odoo — o override é só do
  widget (apresentação), não altera o `sensor_monitor` nem os alarmes reais.
- Config por usuário (segue por site, como o resto do dashboard).

## Testes a cobrir

**Schema (`lib/layout/schema.test.ts`):**
- `OPTIONS_SCHEMA` por tipo: aplica defaults quando `options` ausente/vazio.
- `defaultWindow` inválido → cai no default `'24h'` sem derrubar o layout.
- `scope` inválido → default `'site'`.
- KPI refine em dois níveis:
  - **schema isolado** (`kpiOptions.safeParse`): `limiteMin > limiteMax` → `success:false`
    (o refine reprova); só um dos dois preenchido → válido. (Fonte da validação que o popover
    usa p/ **feedback inline** — ver §UI e testes do popover. NÃO bloqueia o "Salvar" global
    do `DashboardEditor`: o popover é per-widget e não tem botão Salvar; ele só sinaliza o erro
    inline. Se ainda assim um blob com min>max for salvo, o `parseOptions` no reload coage aos
    defaults do tipo — falha segura, sem override, cor segue o `alarm_state` autoritativo.)
  - **via `parseLayout` (invariante crítica):** um blob salvo com `limiteMin > limiteMax`
    **não derruba o layout** — `parseOptions` cai nos defaults do tipo KPI e o dashboard do
    operador sobrevive (nunca cai no `defaultLayout` por causa de uma option ruim).
- Backward-compat: blob antigo (`{ scope: 'site' }`, sem os campos novos) parseia e ganha
  defaults; `version` continua `1`.
- **Tipagem/tsc:** confirmar que o tipo estático de `WidgetInstance.options` permanece
  `Record<string, unknown>` (inalterado) e que `tsc -b` segue verde **sem** tocar em
  `registry.tsx`/`WidgetConfigPopover`/`newWidget`/`DashboardEditor` — a validação de `options`
  é só em runtime (ver §Mecanismo/Tipagem).

**Registry (`registry.test`):**
- `timeseries` passa `defaultWindow` de `options` para o widget.
- `alarms` passa `scope` + `binding.areaCode` corretos.
- `kpi` passa `limiteMin`/`limiteMax` de `options`.

**WidgetConfigPopover (`WidgetConfigPopover.test.tsx`):**
- `timeseries`: mostra o `WindowSelector`; escolher janela chama `onChange` com
  `options.defaultWindow` atualizado.
- `kpi`: editar limite mín./máx./label chama `onChange` com os campos certos; placeholder
  mostra o threshold herdado do sensor quando vazio.
- `alarms`: trocar escopo para "Área" revela o select de área; escolher área grava
  `binding.areaCode`; voltar para "Site" mantém `scope: 'site'`.
- Popover é montado só em modo edição (via `WidgetFrame` `editing && open`).

**Widgets:**
- `KpiWidget` (semântica `max`): com override, valor **fora** da faixa → `crit` mesmo que
  `alarm_state==='ok'`; valor **dentro** da faixa mas `alarm_state==='crit'` (backend) →
  **continua `crit`** (override nunca rebaixa); valor dentro + `alarm_state==='ok'` →
  `--color-ink`. Sem override → cor segue só `alarm_state`, idêntico ao atual (sem query nova).
- **Guarda anti-regressão A2:** teste explícito de que um override "dentro da faixa" **não**
  pinta de verde um KPI cujo `alarm_state` do backend é `warn`/`crit`.
- `TimeseriesWidget`: `defaultWindow` das options é a janela inicial.
- `AlarmsWidget`: `scope: 'area'` + `areaCode` filtra; `scope: 'area'` sem `areaCode` cai no
  painel de site (não quebra).

**Persistência (edição, mock `saveLayout`):**
- Editar uma option, "Salvar" → `saveLayout` chamado com o layout contendo a `options` nova.
- "Cancelar" reverte a cópia local (option não persiste).
