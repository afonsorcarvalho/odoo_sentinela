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

## 3. Design visual — direção "instrumento calibrado"

> `demo_dashboard.html` **deixa de ser** a fonte da verdade visual. Direção nova,
> derivada das skills `frontend-design` + `impeccable`, voltada à usabilidade de
> **enfermeiros e responsáveis técnicos** em ambiente de CME.

**Cena de uso (força as decisões)**: um enfermeiro de luvas olha um tablet de parede
numa antessala de CME sob luz fluorescente e precisa saber, em menos de dois segundos,
se a sala de esterilização está dentro da faixa segura; mais tarde o responsável técnico
revisa a mesma tela no desktop para atestar conformidade RDC 15. Isso impõe:
glanceabilidade a distância, alvos grandes (luvas), alto contraste (segurança) e leitura
que não dependa só de cor (daltonismo + rigor regulatório).

**Cor = significado, nunca decoração.** Num monitor de segurança, o trio de status
(verde `ok` / âmbar `warn` / vermelho `crit`) representa o estado ambiental e **nada
mais**. Consequência de design: o primary da marca **não pode** ser âmbar (colidiria com
`warn`) nem verde/vermelho. O seed âmbar sugerido pela paleta é **rejeitado** por esse
motivo.

**Estratégia de cor: Restrained → quase-monocromático.**
- UI em cinza-frio de instrumento (grafite/neutros frios). A interface fica quieta; o
  status é a única cor forte e por isso salta.
- **Primary** (azul-frio, ~`oklch(0.55 0.13 245)`) usado **só** para interativo:
  seleção, foco, ação primária, chip de janela ativo. Nunca decorativo.
- Status: `good ~oklch(0.65 0.16 150)`, `warn ~oklch(0.72 0.15 75)`,
  `crit ~oklch(0.58 0.19 25)` — clareados no tema escuro. Valores finais afinados no
  build com verificação de contraste (corpo ≥4.5:1).
- **Status nunca só por cor**: sempre acompanhado de ícone + rótulo textual
  ("Dentro da faixa" / "Perto do limite" / "Fora da faixa").

**Tema**: light é o default (ambiente clínico claro, glanceabilidade); dark serve
estação de monitoramento noturna/escurecida. Ambos desde já — não um derivado do outro,
cada um afinado (bg light ~branco puro; bg dark ~preto-frio `oklch(0.16 0.008 245)`).

**Tipografia**: uma família UT-sans (Inter/system) para toda a interface + **mono
tabular** (ex. Geist Mono / IBM Plex Mono) exclusivo para os **valores de leitura** —
reforça o caráter de instrumento. Escala rem fixa (não fluida), numerais tabulares.

**Assinatura — o readout calibrado.** O valor ao vivo (decisão do usuário: numérico, não
radial) é renderizado como leitura de instrumento: valor grande em mono tabular + unidade,
com um **trilho de tolerância** fino logo abaixo — `min ──────●────── max` — onde o ponto
mostra a posição do valor corrente dentro da faixa segura. Centro = verde; perto da borda
= âmbar; fora = vermelho. É glanceável a distância e **amarra visualmente** com as
`markLines` de limite do gráfico (mesma faixa min/max, mesma linguagem). Este é o único
elemento "memorável"; o resto fica disciplinado.

**Movimento**: só estado (150–250 ms). Atualização do valor com transição sutil; mudança
de estado de alarme dispara **um** pulso de atenção. Sem coreografia de load. Respeita
`prefers-reduced-motion` (crossfade/instantâneo).

Tokens vivem no `tailwind.config` (OKLCH), herdados por toda a SPA. `frontend-design` +
`impeccable` continuam guiando o build.

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
├── LiveReadout        — readout calibrado: valor mono tabular + unidade + estado
│                        (ícone+rótulo) + trilho de tolerância (min──●──max)
├── WindowSelector     — chips 1h/24h/7d/30d (dispara refetch histórico)
├── ThresholdBadge     — mostra min/max vigente e se é padrão regulatório
└── TimeSeriesChart    — ECharts: histórico + cauda ao vivo (appendData) + markLines de limite
```

Cada componente é testável isolado com fixtures. Estado ao vivo: página assina
`liveApi`, mantém buffer da cauda em estado local, passa ao readout (último valor +
posição no trilho) e ao chart (append incremental). Troca de janela invalida só a query
de histórico; a cauda ao vivo persiste.

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
5. `LiveReadout`: estado por `alarm_state` (cor **+ ícone + rótulo**, não só cor),
   unidade correta, e posição do ponto no trilho de tolerância bate com o valor/limites.
6. Estados de erro/reconexão renderizam corretamente.

## 10. Entregáveis desta fatia

- `frontend/` scaffold Vite+React+TS rodando.
- `frontend/CONTRACTS.md` — contrato de-facto dos 3 transportes.
- `tailwind.config` com tokens OKLCH da direção "instrumento calibrado" (light+dark),
  contraste verificado (corpo ≥4.5:1).
- `lib/api/` com os 3 adapters (interface + impl mock).
- Tela Detalhe do Sensor completa com os 4 componentes.
- Suite de testes verde.

## 11. Próximas fatias (fora daqui)

Overview → site→área → painel de alarmes (com ciclo de vida via Odoo) → relatórios RDC 15.
Integração real substitui os mocks quando a Fase 3 existir — sem tocar componentes,
só a impl dos adapters e `VITE_API_MODE=real`.
