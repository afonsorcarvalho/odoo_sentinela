# Design — Frontend Sentinela CME: fatia fina "Detalhe do Sensor"

> Spec de implementação. Complementa `frontend_spec.md` (arquitetura decidida) e
> `odoo_modelo_dados_spec.md` (nomes de campo reais). Primeira entrega da Fase 4 do
> `roadmap_implementacao.md`, construída contra mocks (Fase 3 ainda não existe).

## 1. Objetivo e escopo

Construir **uma** tela — Detalhe do Sensor — que prova o loop de dados ponta a ponta
do frontend contra dados mockados:

- valor ao vivo (numérico) com estado de faixa;
- gráfico de série temporal histórica com seletor de janela (1h / 24h / 7d / 30d);
- linhas de limite (min/max do threshold) desenhadas sobre o gráfico;
- **cauda ao vivo anexada localmente** ao gráfico a partir do feed SSE, sem refetch.

Fora de escopo desta fatia: overview, site→área, painel de alarmes, ciclo de vida de
alarme, autenticação real. Serão fatias seguintes.

### A prova arquitetural

A fatia não é "um gráfico bonito". O que ela valida é a separação **fetch histórico
(uma vez) + append ao vivo (incremental, sem refetch)** — exatamente o que
`frontend_spec.md` §9 exige. Se o mock apenas refizesse a série num timer, a tela
pareceria certa mas não provaria nada. Portanto o mock SSE **empurra pontos
incrementais** e o gráfico faz `appendData`.

## 2. Stack (decidido em `frontend_spec.md` §7)

- Vite + React + TypeScript (SPA pura, sem Next).
- Tailwind CSS + shadcn/ui.
- TanStack Query (estado de servidor: cache/refetch/invalidação).
- **ECharts** (escolha do usuário sobre uPlot) para a série temporal.
- Cliente SSE nativo (`EventSource`) para a cauda ao vivo — mockado nesta fatia.
- Vitest + Testing Library para testes.

Local do projeto: `odoo_sentinela/frontend/`.

## 3. Design visual

- **Fonte da verdade visual**: `demo_dashboard.html`. Portar os CSS custom properties
  para tokens do `tailwind.config` (teal `--brand:#0e7a82`, `--brand-deep:#0b545a`,
  status `good #0ca30c` / `warn #b8860b` / `crit #d03b3b`, superfícies, sombras).
  A SPA inteira herda o sistema de design, não só esta tela.
- **Dark + light** desde já: tokens definidos para os dois temas; alternância por
  classe/`prefers-color-scheme`. Demo é light — dark derivado dele.
- **Gauge**: valor **numérico simples** grande (não radial), com cor de estado
  (dentro/perto/fora de faixa) e unidade.
- Guiado pelas skills `frontend-design` e `impeccable` na fase de build.

## 4. Seam de troca mock→real (crítico)

"Mocks primeiro" só compensa se as APIs reais entram sem tocar componentes. Regra:
**nenhum componente chama `fetch` ou `EventSource` diretamente.** Tudo passa por
`lib/api/`, com três adapters espelhando os três transportes reais (separados, não um
blob único), selecionáveis por env flag (`VITE_API_MODE=mock|real`):

| Adapter | Dado | Transporte real (Fase 3) | Mock desta fatia |
|---|---|---|---|
| `metaApi` | sensor + threshold | Odoo HTTP | fixtures estáticas |
| `historyApi` | série downsampled | FastAPI sobre Timescale (HTTP) | gerador sintético por janela |
| `liveApi` | cauda ao vivo | SSE (`EventSource`) | emissor de pontos incrementais |

TanStack Query fica **por cima** dos adapters `metaApi`/`historyApi`. O `liveApi`
expõe subscribe/unsubscribe (interface estilo `EventSource`) para o componente anexar
pontos.

## 5. Contrato de mock = contrato de-facto (saída de Fase 0)

Não existe doc de contratos congelado (Fase 0 do roadmap pedia; `frontend_spec.md` §10
delega shapes de endpoint à implementação). Logo, **os shapes definidos aqui são o
contrato de-facto** — registrados deliberadamente em `frontend/CONTRACTS.md`, não como
fixtures descartáveis. Casam com os campos reais do `odoo_modelo_dados_spec.md`.

### 5.1 Sensor meta — de `sensor_monitor.sensor` (+ `area`, `measurement.type`)

```ts
type SensorMeta = {
  sensor_code: string            // sensor_monitor.sensor.sensor_code
  name: string
  unidade: string                // sensor.unidade (ex: "C", "%UR", "Pa")
  protocolo_origem: '4-20ma' | 'rs485' | 'i2c'
  measurement_type: { code: string; name: string }   // measurement.type
  area: { area_code: string; name: string; category: string } // area + area.category
}
```

### 5.2 Threshold — de `sensor_monitor.alarm.threshold`

```ts
type Threshold = {
  sensor_id: string              // referencia sensor_code
  limite_min: number
  limite_max: number
  is_valor_padrao_regulatorio: boolean
}
```

### 5.3 History — da API de leitura (Timescale)

Janela curta (1h) devolve pontos crus; janelas longas devolvem agregado (continuous
aggregates: min/max/avg). A resposta declara sua resolução.

```ts
type HistoryPoint =
  | { ts: number; value: number }                       // resolução 'raw'
  | { ts: number; min: number; max: number; avg: number } // resolução 'agg'
type HistoryResponse = {
  sensor_code: string
  window: '1h' | '24h' | '7d' | '30d'
  resolution: 'raw' | 'agg'
  points: HistoryPoint[]
}
```

### 5.4 Live — do feed SSE

Evento incremental, um ponto por vez:

```ts
type LivePoint = {
  sensor_code: string
  ts: number
  value: number
  alarm_state: 'ok' | 'warn' | 'crit'
}
```

## 6. Componentes

```
SensorDetailPage
├── LiveGauge          — valor numérico corrente + estado (cor) + unidade
├── WindowSelector     — chips 1h/24h/7d/30d (dispara refetch histórico)
├── ThresholdBadge     — mostra min/max vigente e se é padrão regulatório
└── TimeSeriesChart    — ECharts: histórico + cauda ao vivo (appendData) + markLines de limite
```

Cada componente é testável isolado com fixtures. Estado ao vivo: página assina
`liveApi`, mantém buffer da cauda em estado local, passa ao gauge (último valor) e ao
chart (append incremental). Troca de janela invalida só a query de histórico; a cauda
ao vivo persiste.

## 7. Fluxo de dados

```
metaApi.getSensor(code) ─┐
metaApi.getThreshold(code)┼─ TanStack Query ─→ LiveGauge / ThresholdBadge / markLines
historyApi.getHistory(code, window) ─ TanStack Query ─→ TimeSeriesChart (série base)
liveApi.subscribe(code) ─ EventSource-like ─→ buffer local ─→ gauge (últ.) + chart.appendData
```

## 8. Tratamento de erro / estados

- Loading skeletons por painel (não spinner global).
- Erro de `metaApi`/`historyApi`: estado de erro no painel afetado, com retry (TanStack
  Query retry + botão).
- `liveApi` desconectado: badge "ao vivo" vira "reconectando"; gráfico mantém histórico;
  reconecta automático (mock simula queda/volta).
- Sem threshold configurado: gráfico sem markLines, badge indica "sem limite".

## 9. Testes (Vitest + Testing Library)

1. `liveApi` mock emite pontos **incrementais** (não a série inteira) num intervalo.
2. Chart **anexa** pontos ao vivo sem refazer a query de histórico.
3. `markLines` correspondem a `limite_min`/`limite_max` do threshold.
4. Trocar janela dispara novo fetch de histórico e re-render do eixo.
5. `LiveGauge` colore por `alarm_state` e mostra unidade.
6. Estados de erro/reconexão renderizam corretamente.

## 10. Entregáveis desta fatia

- `frontend/` scaffold Vite+React+TS rodando.
- `frontend/CONTRACTS.md` — contrato de-facto dos 3 transportes.
- `tailwind.config` com tokens do `demo_dashboard.html` (light+dark).
- `lib/api/` com os 3 adapters (interface + impl mock).
- Tela Detalhe do Sensor completa com os 4 componentes.
- Suite de testes verde.

## 11. Próximas fatias (fora daqui)

Overview → site→área → painel de alarmes (com ciclo de vida via Odoo) → relatórios RDC 15.
Integração real substitui os mocks quando a Fase 3 existir — sem tocar componentes,
só a impl dos adapters e `VITE_API_MODE=real`.
