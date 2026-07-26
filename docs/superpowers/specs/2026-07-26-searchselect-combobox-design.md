# SearchSelect — combobox pesquisável genérico + "Pesquisar mais"

**Data:** 2026-07-26
**Status:** aprovado, pronto para plano
**Escopo:** frontend (`frontend/src`), dashboard modo edição

## Problema

Hoje o `WidgetConfigPopover` escolhe área/sensor com `<select>` nativo: sem
filtro por digitação e sem busca por outros campos. Com dezenas de sensores/áreas
fica ruim de achar o item. O multi-área do alarms usa um dropdown "Adicionar
área" + chips, também sem filtro.

Queremos um componente **genérico e reutilizável** de seleção — usado sempre que
for preciso escolher área, sensor (e no futuro cliente, hub, coletor, etc.) —
com:
- filtro por digitação (combobox),
- um "Pesquisar mais" que abre busca por outros campos, estilo Odoo many2one
  ("Search More…").

## Objetivo / critérios de sucesso

1. Existe um `SearchSelect<T>` genérico que não conhece "área"/"sensor" — opera
   sobre `items: T[]` + um objeto de config.
2. Filtra por digitação (inline, casa no rótulo).
3. "Pesquisar mais" abre modal-tabela com colunas por campo e uma busca que casa
   em **todos** os campos configurados; selecionar uma linha escolhe o item.
4. Suporta single e multi-select (multi = chips + checkboxes na modal).
5. Adotado no `WidgetConfigPopover` nos 3 pontos: Área (single), Sensor (single),
   multi-área do alarms (multi).
6. Adicionar uma entidade nova no futuro = escrever 1 objeto de config (+ wrapper
   opcional), **sem** tocar em `SearchSelect`/`SearchMoreDialog`.

## Não-objetivos (YAGNI)

- Nenhuma API de busca no servidor: todos os dados (sensores → áreas derivadas)
  já vêm client-side via `useSensors()`. Busca é 100% em memória.
- Sem paginação/virtualização na modal (dezenas de itens, não milhares). Se algum
  dia a lista crescer muito, vira trabalho separado.
- Sem criar entidade nova pela UI ("Create" do Odoo). Só selecionar existentes.

## Decisões (do brainstorm)

- **Escopo v1:** single + multi, adotando os 3 selects do `WidgetConfigPopover`.
- **"Pesquisar mais":** modal-tabela multi-campo (colunas + 1 caixa de busca que
  casa em todos os campos), Odoo-like.
- **Construção:** adicionar **Downshift** (`useCombobox` / `useMultipleSelection`)
  — teclado + ARIA prontos. Visual AFR e a modal-tabela são nossos (Downshift não
  faz modal).
- **Filtro inline:** casa no rótulo (nome). A busca multi-campo é o papel da
  modal. (Se depois quisermos código no inline, é trivial estender o `searchText`
  usado pelo filtro inline.)

## Arquitetura

Unidades pequenas, com fronteiras claras:

### `SearchSelect<T>` (genérico)
Componente de seleção. Presentational + Downshift. Não conhece a entidade.

Props (união discriminada por `multiple`):
```ts
type EntityConfig<T> = {
  getId: (item: T) => string
  getLabel: (item: T) => string          // rótulo primário (nome)
  getSecondary?: (item: T) => string     // sub-linha: "código · área · tipo"
  searchText: (item: T) => string        // campos concatenados p/ busca da modal
  columns: { header: string; cell: (item: T) => React.ReactNode }[] // modal-tabela
}

type SingleProps<T> = {
  multiple?: false
  items: T[]
  config: EntityConfig<T>
  value: string | null                   // id selecionado
  onChange: (id: string | null) => void
  label?: string                         // rótulo do campo (ex.: "Sensor")
  placeholder?: string
}

type MultiProps<T> = {
  multiple: true
  items: T[]
  config: EntityConfig<T>
  value: string[]                        // ids selecionados
  onChange: (ids: string[]) => void
  label?: string
  placeholder?: string
}
```

Comportamento:
- Single: input de combobox; ao digitar filtra por `getLabel`; dropdown lista
  itens (label + `getSecondary`); rodapé fixo **"Pesquisar mais…"** abre a modal.
  Selecionar fecha o dropdown e mostra o label do item no input.
- Multi: mantém **chips** dos selecionados abaixo do input; dropdown alterna
  (marca/desmarca) itens; "Pesquisar mais…" abre a modal em modo multi.
- Limpar: single tem um "×" p/ voltar a vazio (equivale à opção "—" atual).
- Teclado/ARIA: via Downshift (setas, Enter, Esc, `aria-` de combobox/listbox).

### `SearchMoreDialog<T>` (modal-tabela)
Reusada por single e multi. Abre **sobre** o contexto atual (inclusive sobre o
`WidgetConfigDrawer`, que já é um drawer modal).

- `FloatingPortal` + `FloatingOverlay` (ancestral) + `FloatingFocusManager`
  próprios, `z` acima do drawer. Fechar (Esc/backdrop/✕/Cancelar) fecha **só a
  modal**, não o drawer por baixo. Mesmo padrão de shell do `SensorDetailDrawer`
  / `WidgetConfigDrawer`, com atenção ao empilhamento (dois focus-managers modais
  aninhados; ver Riscos).
- Uma caixa de busca no topo casa em `config.searchText(item)` (lowercase,
  substring). Tabela renderiza `config.columns`.
- Single: clicar na linha seleciona e fecha. Multi: checkbox por linha + botão
  "Confirmar" (aplica o conjunto marcado) e "Cancelar".

### `entityConfigs.ts`
Objetos de config por entidade:
- `areaConfig: EntityConfig<Area>` — label=nome; secondary="código · categoria";
  searchText=nome+código+categoria; columns=[Nome, Código, Categoria].
- `sensorConfig: EntityConfig<SensorMeta>` — label=nome; secondary="código ·
  área · tipo"; searchText=nome+código+área.name+measurement_type.name+unidade+
  protocolo; columns=[Nome, Código, Área, Tipo, Unidade].

(`Area` = `SensorMeta['area']`, isto é `{ area_code, name, category }`.)

### Wrappers finos: `AreaSelect` / `SensorSelect`
Buscam os dados e injetam a config. Fonte de dados fica **fora** do genérico.
```tsx
// SensorSelect: single ou multi, delega ao SearchSelect com sensorConfig
export function SensorSelect(props) {
  const sensors = useSensors().data ?? []
  return <SearchSelect items={sensors} config={sensorConfig} {...props} />
}
// AreaSelect: deriva áreas de useSensors() (Map por area_code) e usa areaConfig
```
São só os dois primeiros consumidores do genérico — não casos especiais dentro
dele. Entidade nova (cliente, hub…) = novo objeto de config (+ wrapper que busca
de onde precisar), sem mexer no `SearchSelect`.

## Fluxo de dados

`useSensors()` → wrapper monta `items` → `SearchSelect` filtra/exibe → `onChange`
devolve id(s) → o chamador (`WidgetConfigPopover`) grava em `widget.binding`
(`areaCode` / `sensorCode` / `areaCodes`), exatamente como hoje. O componente é
controlado: nunca guarda a seleção como fonte de verdade, só reporta via
`onChange` (mesma disciplina do `WidgetConfigPopover`/drawer atuais).

## Adoção no `WidgetConfigPopover`

- Binding **área** (`needs==='area'`): `<AreaSelect value={binding.areaCode ?? null}
  onChange={code => onChange({...widget, binding:{...binding, areaCode: code ?? undefined}})} />`.
- Binding **sensor** (`needs==='sensor'`): `<SensorSelect …sensorCode… />`.
- **Multi-área alarms** (scope==='area'): `<AreaSelect multiple
  value={areaCodesEfetivos} onChange={codes => onChange({...binding, areaCodes: codes})} />`
  — substitui o dropdown "Adicionar área" + render manual de chips (chips passam a
  ser do próprio `SearchSelect`). Mantém a regra de resolução legada
  `areaCodes ?? (areaCode ? [areaCode] : [])` para o valor inicial.

Sem mudança de contrato de dados: `binding` continua gravando os mesmos campos.

## Tratamento de erros / bordas

- `items` vazio (dados ainda carregando): dropdown mostra "Nenhum resultado" /
  modal idem; input utilizável, sem crash.
- Valor selecionado que não existe mais em `items` (ex.: sensor removido): single
  mostra o id cru como fallback do label; multi mantém o chip com o id. Não
  quebra.
- Busca sem match: modal mostra estado vazio ("Nada encontrado").

## Testes

- `SearchSelect` single: filtra ao digitar; seleciona item; limpa (×); teclado
  (Downshift: setas+Enter+Esc); fallback de label p/ id inexistente.
- `SearchSelect` multi: adiciona/remove via dropdown; chips refletem `value`;
  remover chip chama `onChange` sem o id.
- `SearchMoreDialog`: busca casa em campo secundário (não só nome); clicar linha
  seleciona (single); checkboxes + Confirmar (multi); Esc/backdrop fecham só a
  modal.
- `entityConfigs`: `searchText`/`columns` de área e sensor cobrem os campos
  esperados (teste de dados, barato).
- Adoção: atualizar `WidgetConfigPopover.test` p/ os novos componentes,
  preservando as asserções de `onChange`/binding (área, sensor, multi-área,
  incluindo o caminho legado `areaCode → areaCodes`).

## Riscos

- **Modal-dentro-de-drawer:** dois `FloatingFocusManager` modais aninhados
  (drawer + modal). Precisa garantir que a modal fica acima, recebe foco, e que
  fechá-la devolve o foco ao combobox sem fechar o drawer. jsdom não implementa
  `inert`, então validar interação no teste + 1 screenshot Playwright.
- **+1 dependência (Downshift):** aumenta bundle. Aceito pela troca (a11y/teclado
  prontos). Fixar major no `package.json`.
- **Estilo AFR:** Downshift é headless; todo o visual (input, listbox, chips,
  tabela) é nosso — seguir os tokens já usados (`var(--color-*)`,
  `.drawer-panel`, chips do `WidgetConfigPopover`).

## Fora de escopo / futuro

- Virtualização/paginação da modal.
- Criação de entidade pela UI.
- Incluir código no filtro inline (trivial depois).
- Adoção fora do `WidgetConfigPopover` (outros formulários) — o genérico já
  habilita, mas cada adoção é seu próprio passo.
