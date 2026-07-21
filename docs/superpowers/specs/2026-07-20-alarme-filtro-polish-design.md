# Design: Polish do filtro de áreas (chip "Todas" + chips menores)

**Data:** 2026-07-20
**Status:** Aprovado (brainstorm)
**Depende de:** filtro de áreas ao vivo ([2026-07-20-alarme-filtro-area-runtime-design.md](2026-07-20-alarme-filtro-area-runtime-design.md)) — mergeada.

## Contexto

O filtro de áreas do card de alarmes (chips toggle) tem 3 dores de UX levantadas
pelo usuário: (1) chips grandes demais; (2) isolar uma área exige desmarcar todas as
outras uma a uma; (3) voltar a "todas" exige remarcar tudo. Pesquisa de padrões
(Plotly/ECharts legend, Kibana, Metabase, MUI/React-Aria, WCAG target-size — ver
`scratchpad/pesquisa-filtro-ux.md`) apontou: evitar gestos ocultos (hover/double-tap/
long-press/modifier — todos falham com luva) e usar um controle **"Todas"** explícito.
Decisão do usuário: modelo **"Todas" toggle-all** (tap na área continua sendo
liga/desliga, sem ambiguidade).

## Comportamento

### Chip "Todas" (novo, primeiro da linha)

Estado de 3 valores via `aria-pressed`, derivado do filtro atual vs o universo de áreas:
- **Todas ativas** → `aria-pressed="true"` (destacado). Tap → **limpa** (nenhuma ativa).
- **Subconjunto** (≥1 e < todas) → `aria-pressed="mixed"`. Tap → **ativa todas**.
- **Nenhuma** ativa → `aria-pressed="false"`. Tap → **ativa todas**.

Resultado: isolar uma = tap "Todas" (limpa) + tap a área = **2 toques** (antes N−1);
voltar a todas = tap "Todas" = **1 toque**.

O universo de áreas continua sendo a **união** de áreas-de-sensores + áreas-dos-alarmes
(invariante crítica da feature anterior: nenhum alarme fica sem chip / invisível). O
"limpa"/"ativa todas" opera sobre esse mesmo universo.

### Chips de área (existentes)

- Tap = liga/desliga — **comportamento inalterado**.
- **~50% menores no visual:** fonte menor (ex.: `text-[11px]`), padding horizontal/vertical
  reduzido, altura visual do "pill" ~metade da atual.
- **Área tocável preservada ≥ ~44px:** o botão mantém `min-h-11` (44px) como alvo de
  toque (uso com luva / WCAG 2.5.5); o pill visual menor fica centrado, com o padding
  transparente completando a hit-area. Ou seja: **50% menos peso visual, NÃO 50% menos
  alvo.** Gap entre chips ≥ 8px (`gap-2`).

### Estados vazios

- Nenhuma área ativa (usuário limpou via "Todas") → o painel segue mostrando
  **"Nenhuma área selecionada"** (já implementado; distinto de "Nenhum alarme ativo.").

### Acessibilidade

- Chips e "Todas" continuam `<button>` com `aria-pressed`. "Todas" usa o 3º estado
  `"mixed"` quando subconjunto (padrão tri-state de toggle-all).
- `role="group"` com `aria-label` (ex.: "Filtrar por área") envolvendo a linha, se ainda
  não houver.
- Cada chip mantém texto = nome da área (rótulo acessível).

## Escopo — enxuto

- Só `frontend/src/components/widgets/AlarmsWidget.tsx` (+ `AlarmsWidget.test.tsx`).
- Sem schema/registry/backend/config. Sem mudança no `AlarmPanel` (a linha de chips já é
  passada como `filtro` pelo AlarmsWidget).

## Fora de escopo

- Ação "só esta" por chip em 1 toque (fase 2 opcional; ocuparia espaço, briga com chips
  menores).
- Gestos (double-tap/long-press/hover/modifier) — rejeitados (touch/luva).
- Persistir o filtro (continua de sessão).

## Testes a cobrir

`AlarmsWidget` (com `useSensors`/`useAlarms` mockados; áreas do universo conhecidas):
- Chip "Todas" presente, primeiro da linha.
- Todas ativas (default scope='site') → "Todas" `aria-pressed="true"`.
- Tap "Todas" com todas ativas → limpa (todos os chips de área `aria-pressed="false"`;
  painel "Nenhuma área selecionada").
- A partir de "nenhuma", tap "Todas" → ativa todas (todos os chips `aria-pressed="true"`).
- Subconjunto (desativar 1 área) → "Todas" `aria-pressed="mixed"`.
- Isolar em 2 toques: tap "Todas" (limpa) → tap área X → só alarmes de X; "Todas" volta a
  `"mixed"`.
- Voltar a todas em 1 toque: de um subconjunto, tap "Todas" → todos os alarmes de volta.
- Tap numa área continua sendo liga/desliga individual (não regride).
- (a11y) chips e "Todas" com `aria-pressed`; "Todas" assume `"mixed"` no subconjunto.
- (visual/tap target — ⚠️ Playwright) chip menor porém altura tocável ~44px.
