# Design: Filtro de áreas ao vivo no card de alarmes

**Data:** 2026-07-20
**Status:** Aprovado (brainstorm)
**Depende de:** alarme multi-área ([2026-07-20-alarme-multi-area-design.md](2026-07-20-alarme-multi-area-design.md)) — mergeada.

## Contexto

O `AlarmsWidget` filtra alarmes por escopo salvo na config (`scope` site/área +
`binding.areaCodes`). Falta **transparência + controle ao vivo**: o operador não vê de
relance quais áreas o card está mostrando, nem consegue ajustar sem editar a config.

Objetivo: o card de alarme ganha uma **linha de chips de área** (todas as áreas do
site), cada um um toggle ativo/inativo. Os chips **são** a transparência (mostram quais
áreas estão exibindo) e o controle (o operador liga/desliga áreas ao vivo). A config
passa a definir o **default** desse filtro.

## Decisões de brainstorm

- **Universo dos chips = todas as áreas do site.** A config só predefine quais vêm
  ativas; o operador pode ativar qualquer área ao vivo, mesmo fora da config.
- **Filtro é de sessão (reseta no reload).** A config é a fonte da verdade do default
  salvo; o ajuste ao vivo é temporário (`useState`, não persiste no blob). Evita
  redundância "dois lugares editando a mesma coisa".

## Comportamento

### Estado e default

- `AlarmsWidget` mantém `areasAtivas: Set<string>` (estado de sessão).
- **Default ativo** (init do estado), derivado da config:
  - `scope === 'area' && areaCodes.length > 0` → `new Set(areaCodes)`.
  - `scope === 'site'` **ou** `areaCodes` vazio → todas as áreas do site ativas.
- O default é computado no init do `useState`. **Nota de implementação:** as áreas do
  site vêm de `useSensors` (assíncrono); inicializar o Set só quando os sensores
  chegarem (ex.: lazy init + efeito que semeia o default na primeira carga, ou derivar
  o "efetivo" = `areasAtivas ?? default` enquanto o estado é `null`). Escolher a forma
  que evite semear vazio antes dos sensores carregarem.

### Universo de áreas

- Todas as áreas do site, deduplicadas de `useSensors` (`s.area.area_code` +
  `s.area.name`), ordenadas de forma estável (ex.: por nome). Cada uma vira um chip.

### Chips (toggle)

- Cada chip mostra o nome da área. **Ativo:** destaque (fundo/borda de acento, ex.:
  `--color-primary`/`--color-panel`). **Inativo:** apagado (`--color-muted`, fundo
  neutro). Clicar alterna a presença da área em `areasAtivas`.
- Tap target ≥ 44px de altura (`min-h-11` ou padding equivalente) — uso com luvas.
- A11y: cada chip é um `<button>` com `aria-pressed={ativa}` e texto do nome da área.
- Linha de chips com `flex-wrap` (painel estreito quebra em várias linhas).

### Filtragem

- Alarmes exibidos = `alarms.filter(a => areasAtivasEfetivas.has(a.area_code))`.
- **Nenhuma área ativa** (operador desligou todas): o painel mostra estado explícito
  **"Nenhuma área selecionada"** (`--color-muted`), **distinto** de "Nenhum alarme
  ativo." — não confundir vazio-por-filtro com sem-alarme. É ação explícita e
  reversível do operador (clicar um chip volta a mostrar), então não é o mesmo risco do
  fallback de config vazia.
- A contagem de ativos no badge do header reflete os alarmes **já filtrados**.
- A modal "Ver mais" recebe os **mesmos alarmes filtrados**.

## Onde fica a lógica

- **`AlarmsWidget.tsx`** (dono do estado): computa `todasAreas` (de `useSensors`), o
  default (da config), mantém `areasAtivas`, monta os chips (toggle) e filtra os
  alarmes. Passa a linha de chips e os alarmes filtrados ao `AlarmPanel`; passa os
  filtrados à `AlarmsModal`.
- **`AlarmPanel.tsx`**: ganha prop **opcional** `filtro?: ReactNode`, renderizada logo
  abaixo da linha do header ("Alarmes" + badge) e acima da lista. Opcional para não
  quebrar outros usos do `AlarmPanel` (ex.: `DashboardPage`), que passam sem `filtro`.
  Também precisa distinguir "nenhuma área selecionada" de "nenhum alarme" — via uma prop
  opcional `mensagemVazio?: string` (default "Nenhum alarme ativo.") OU o `AlarmsWidget`
  decide a mensagem e passa. Escolher a forma mais simples que mantenha `AlarmPanel`
  genérico.
- A config (multi-área) **não muda** — `scope`/`areaCodes` continuam como estão, agora
  interpretados como o **default** do filtro ao vivo.

## Relação com a config (semântica)

- Backward-compat total: na carga, o card mostra exatamente as áreas da config (como
  hoje), só que agora com os chips visíveis e toggltáveis. Config legada (`areaCode`
  single) resolve para o default via a mesma fórmula do registry/popover.
- `scope='site'` = default todas ativas. `scope='area'` = default = `areaCodes`.

## Escopo — fase 1 (enxuto)

- `AlarmsWidget.tsx`, `AlarmPanel.tsx`, `AlarmsModal.tsx` (alarmes filtrados) + testes.
- Sem schema/API/backend novo. Sem persistência do filtro (sessão).

## Fora de escopo

- Persistir o filtro ao vivo no layout (é sessão; a config é o default salvo).
- Filtro por outros critérios (severidade, tipo de violação, período) — só área.
- Mudar a config/UI do popover (multi-área já feita; permanece como default).
- "Selecionar todas / limpar" como botão dedicado — se surgir necessidade, fase futura
  (os chips individuais já cobrem o caso).

## Testes a cobrir

`AlarmsWidget` (com `useSensors`/`useAlarms` mockados):
- Default `scope='area'` + `areaCodes=['a','b']` → chips de a,b ativos; chips das outras
  áreas do site presentes e inativos; alarmes só de a,b.
- Default `scope='site'` → todos os chips ativos; todos os alarmes.
- Clicar um chip inativo (área 'c') → passa a mostrar alarmes de c também (`aria-pressed`
  vira true).
- Clicar um chip ativo → some os alarmes daquela área.
- Desativar TODAS → painel mostra "Nenhuma área selecionada" (≠ "Nenhum alarme ativo.").
- Config legada (`areaCode='a'`, sem `areaCodes`) → chip 'a' ativo por default.
- A modal "Ver mais" recebe os alarmes filtrados (não os do site inteiro).

`AlarmPanel`:
- Com `filtro` (ReactNode) → renderiza os chips sob o header; sem `filtro` → layout
  atual inalterado (uso do `DashboardPage` não quebra).
- Distingue "nenhuma área selecionada" de "nenhum alarme ativo".
