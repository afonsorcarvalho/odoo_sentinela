# TODO — Sentinela

## Em curso
- <nada ainda>

## Pendente
- **Extrair `resolveAreaCodes(binding)`** (follow-up multi-área). A fórmula `areaCodes ?? (areaCode ? [areaCode] : [])` está duplicada em `registry.tsx` e `WidgetConfigPopover.tsx` — extrair helper compartilhado p/ evitar divergência silenciosa. Minor.
- **Freshness em KpiWidget + SensorDetailDrawer** (follow-up da A2). Hoje coloram 1 sensor pelo `alarm_state` cru, sem freshness — um sensor offline lê "verde/OK" nesses widgets enquanto o AreaCard do mesmo sensor mostra offline. Mesma classe "silêncio lido como OK" que a A2 matou no AreaCard, sobrevivendo noutra superfície. Estender `freshness()` a esses dois widgets.
- **A2 fase 2 — fechar o gap "morto no page-load"** (backend). Precisa de `last_seen_ts` autoritativo por sensor (no snapshot/meta) e/ou consumir o alarme `sensor_offline` do backend, para detectar sensor já morto antes da carga (a fase 1, client-side por idade, só pega degradação observada + escala `never` após graça de 10min). Ver Dependências §3 da spec da A2.
- **Thresholds de freshness configuráveis** (`stale_ms`/`offline_ms` via `DashboardConfig`, globais e/ou por sensor) — hoje fixos em `lib/freshness.ts` (5/15 min). Idealmente derivados da cadência de amostragem esperada.

## Feito
- 2026-07-20 — **Escopo de alarme por múltiplas áreas**. `AlarmsWidget` scope='área' passa a aceitar várias áreas (`binding.areaCodes[]`); UI dropdown "adicionar área" + chips removíveis no popover; backward-compat com `areaCode` legado; vazio→site. Mergeada (`f7252c9`). Spec: [2026-07-20-alarme-multi-area-design.md](docs/superpowers/specs/2026-07-20-alarme-multi-area-design.md).
- 2026-07-20 — **A2 — Indicador de sensor offline / dado velho** (dashboard). freshness puro + relógio `useNow` + agregação `offline→≥warn` (sensor parado nunca deixa a área verde) + visual (badge/`—`/marcador de offline). Fase 1 (client-side); prereq de unidade do `ts` resolvido (backend manda ms) e cadência validada (~1/min). Mergeada em master (`0fbf89b`). Spec: [2026-07-19-sensor-offline-stale-data-design.md](docs/superpowers/specs/2026-07-19-sensor-offline-stale-data-design.md).
- 2026-07-20 — **D3 — Drill-down de widget → detalhe do sensor**. Religou o `SensorDetailPanel` (código morto) via drawer lateral + fix de altura DT/M2. Mergeada.
- 2026-07-20 — **B2 — Config por widget via UI** (janela do gráfico, threshold do KPI, escopo do alarme). Mergeada.
- 2026-07-20 — **A3 — Reconexão SSE visível** (badge AO VIVO reflete estado da conexão). Mergeada.
- 2026-07-20 — **A1 — Error boundary por widget** (widget quebrado não derruba o dashboard). Mergeada.
