# Design: Escopo de alarme por múltiplas áreas

**Data:** 2026-07-20
**Status:** Aprovado (brainstorm)
**Depende de:** config por widget ([2026-07-19-widget-config-per-widget-design.md](2026-07-19-widget-config-per-widget-design.md), B2) — mergeada.

## Contexto

O `AlarmsWidget` (B2) tem escopo `site` (todos os alarmes) ou `area` (uma única
área, via `binding.areaCode`). Hoje `AlarmsWidget.tsx` filtra
`all.filter(a => a.area_code === areaCode)` quando `scope==='area' && areaCode`, e o
`WidgetConfigPopover` revela um único dropdown de área. Objetivo: quando o escopo é
`area`, permitir selecionar **várias áreas** do site (ex.: um painel "Esterilização"
que junta Preparo + Arsenal), não só uma.

## Decisão de abordagem

Filtragem **client-side**, como hoje (o `useAlarms` já traz os alarmes do site; nada
de backend/contrato novo). A mudança é: (a) modelo de dados passa a carregar uma
**lista** de áreas; (b) o filtro usa `includes`; (c) a UI vira **dropdown multi +
chips**.

## Modelo de dados

`lib/layout/schema.ts` — `widgetInstanceSchema.binding` ganha `areaCodes`:

```ts
binding: z.object({
  areaCode: z.string().optional(),                 // legado (single) — mantido p/ backward-compat
  areaCodes: z.array(z.string()).optional(),       // novo: multi-área
  sensorCode: z.string().optional(),
})
```

- **Áreas efetivas** (regra única de resolução, usada pelo registry):
  `areaCodes ?? (areaCode ? [areaCode] : [])`.
  Configs antigas (só `areaCode`) continuam funcionando, mapeadas para `[areaCode]`.
- **Migração:** ao editar pela UI nova, o popover grava em `binding.areaCodes` (e pode
  deixar `areaCode` como está — a resolução prefere `areaCodes` quando presente). Sem
  bump de `version` (aditivo/retrocompatível, defaults cobrem tudo — mesma política do B2).
- `alarmsOptions.scope` (site/area) permanece inalterado. As áreas moram no `binding`
  (como o `areaCode` de hoje), não em `options`.

## Filtragem — `AlarmsWidget`

Assinatura muda de `areaCode?: string` para `areaCodes: string[]`:

```ts
export function AlarmsWidget({ scope, areaCodes }: { scope: 'site' | 'area'; areaCodes: string[] })
```

- `scope === 'area' && areaCodes.length > 0` → `all.filter(a => areaCodes.includes(a.area_code))`.
- `scope === 'area' && areaCodes.length === 0` → **todos** (fallback site). Decisão de
  brainstorm: um widget de área sem nenhuma área marcada mostra o site inteiro em vez de
  ficar silencioso (não esconde alarme; não bloqueia salvar). Alinhado à degradação
  segura do B2.
- `scope === 'site'` → todos, como hoje (`areaCodes` ignorado).

A modal "Ver mais" e `areaNameByCode` seguem iguais (recebem a lista já filtrada).

## Registry — resolução no boundary único

`registry.tsx` (o único ponto que traduz binding/options → props) resolve as áreas
efetivas com o fallback legado:

```ts
alarms: {
  ...
  render: (w) => <AlarmsWidget
    scope={(w.options?.scope as 'site' | 'area') ?? 'site'}
    areaCodes={w.binding.areaCodes ?? (w.binding.areaCode ? [w.binding.areaCode] : [])} />,
}
```

Assim o widget nunca conhece o campo legado — recebe sempre uma lista já resolvida.

## UI — `WidgetConfigPopover` (scope='área')

Substitui o dropdown único de área (que hoje o popover monta para alarms quando
`scope==='area'`) por **dropdown multi + chips**:

- Um `<select>` "Adicionar área" cuja lista mostra **apenas as áreas ainda não
  escolhidas** (as já em `areaCodes` somem das opções). Escolher uma adiciona ao
  `binding.areaCodes` e o select volta ao placeholder.
- Abaixo, os **chips** das áreas escolhidas (nome + `×`). Clicar no `×` remove aquela
  área de `binding.areaCodes`.
- Tudo flui pelo `onChange({ ...widget, binding: { ...binding, areaCodes: next } })` já
  existente. Nada de escrita direta no servidor.
- A11y: `<label>` no select; cada chip com botão `×` rotulado (`aria-label="Remover área <nome>"`).
- Estilo/tokens atuais do popover (`--color-surface`/`--color-muted`/`text-xs`); chips
  reusam o padrão visual de badge/StatusChip do projeto onde couber.
- Ao abrir um widget legado (só `areaCode`), o popover mostra esse único como chip
  (resolve `areaCodes ?? [areaCode]` para exibição) e, na primeira edição, grava
  `areaCodes`.

## Escopo — fase 1 (enxuto)

- Só o `AlarmsWidget` ganha multi-área. `scope` continua site/area (não há "multi-site").
- Arquivos: `lib/layout/schema.ts`, `lib/widgets/registry.tsx`,
  `components/widgets/AlarmsWidget.tsx`, `components/WidgetConfigPopover.tsx` (+ testes).
- Sem backend/API/contrato novo (filtragem client-side).

## Fora de escopo

- Filtragem de alarmes por área no backend (continua client-side).
- Selecionar áreas de **outros sites** (o dashboard é por site).
- Migração destrutiva do campo `areaCode` legado (mantido; resolução prefere `areaCodes`).
- Multi-seleção nos outros widgets (area/kpi/timeseries continuam single-binding).
- `version: 2` do schema (mudança é aditiva/retrocompatível).

## Testes a cobrir

**Schema (`schema.test.ts`):**
- `binding.areaCodes` array de strings valida; ausência é ok (opcional).
- Backward-compat: blob antigo com só `areaCode` parseia; `version` continua 1.

**Registry (`registry.test`):**
- alarms com `binding.areaCodes: ['a','b']` → passa `areaCodes=['a','b']`.
- alarms legado (só `binding.areaCode='a'`) → passa `areaCodes=['a']`.
- alarms sem área → passa `areaCodes=[]`.

**AlarmsWidget (`AlarmsWidget.test.tsx`):**
- `scope='area'`, `areaCodes=['a','b']` → mostra só alarmes de a e b (exclui c).
- `scope='area'`, `areaCodes=[]` → mostra todos (fallback site).
- `scope='site'` → todos, `areaCodes` ignorado.
- Alarme de uma área não selecionada não aparece.

**WidgetConfigPopover (`WidgetConfigPopover.test.tsx`):**
- scope='área': dropdown lista só áreas não escolhidas; escolher uma adiciona chip +
  grava `binding.areaCodes` via `onChange`.
- Remover chip (×) tira a área de `binding.areaCodes`.
- Widget legado (`areaCode='a'`) abre mostrando o chip de 'a'; adicionar 'b' grava
  `areaCodes=['a','b']`.
- Voltar escopo p/ 'site' não exige áreas (some a seção de áreas).
