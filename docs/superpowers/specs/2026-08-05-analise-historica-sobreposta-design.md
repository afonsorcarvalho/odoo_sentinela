# Análise histórica sobreposta por área

Data: 2026-08-05
Status: aprovado (design)

## Problema

O dashboard mostra um sensor por widget. Não há como olhar dois sensores da
mesma área lado a lado no mesmo eixo do tempo — que é justamente o gesto de
análise: a temperatura subiu quando a pressão diferencial caiu? O widget de
timeseries também está preso a quatro janelas fixas (1h/24h/7d/30d) ancoradas
em "agora", então "o turno da noite de terça passada" é inalcançável.

## Escopo

Uma página `/analise` no SPA onde o usuário escolhe uma área, sobrepõe vários
sensores dessa área num único gráfico, e navega o tempo por zoom contínuo — a
resolução do dado troca sozinha conforme a janela, como o zoom de um mapa.

Restrições de produto definidas pelo usuário:

- Sensores sempre **da mesma área**. Não há sobreposição entre áreas.
- **No máximo duas unidades distintas** no mesmo gráfico: uma no eixo Y
  esquerdo, outra no direito. Tentar incluir uma terceira unidade é bloqueado
  com aviso, não acomodado com um terceiro eixo.
- Zoom contínuo com resolução automática, mais escolha manual de bucket
  (minuto, hora, dia, semana, mês) com estatísticas mín/máx/média.

Fora de escopo (decidido, não esquecido):

- Cauda ao vivo (`useLiveTail`). N assinaturas SSE numa tela de análise
  histórica é complexidade sem retorno; ao vivo é o dashboard.
- Sobreposição entre áreas diferentes.
- Exportar o gráfico ou os dados.
- Alterar o `TimeseriesWidget` ou o `chartOption.ts` existentes.

## Parte A — Backend

### A.1 Escada de resolução

A cadência real do acervo é ~10 s por sensor (medido: 370k linhas, 6 sensores,
13 dias). Isso posiciona cada degrau:

| Bucket | Origem | Span máximo | Pontos/série no limite |
|---|---|---|---|
| `raw` | `sensor_reading` | 3 h | ~1080 |
| `minuto` | `sensor_reading_minutely` (nova) | 36 h | 2160 |
| `hora` | `sensor_reading_hourly` | 90 d | 2160 |
| `dia` | `sensor_reading_daily` | 5 anos | 1825 |
| `semana` | rollup de `sensor_reading_daily` | 20 anos | 1043 |
| `mes` | rollup de `sensor_reading_daily` | — | — |

O degrau de **minuto** não é enfeite. Sem ele, o salto de `raw` (3 h) para
`hora` faz um span de 12 h renderizar 12 pontos — um penhasco, não um zoom. A
CAgg de minuto custa ~112 mil linhas no volume atual.

O limite de cada degrau é o span em que ele ainda cabe em ~2000 pontos por
série. A regra vive em dois lugares — no backend (`bucket=auto`) e no frontend
(`escolherBucket`, para saber a chave de cache antes da resposta).

Duas tabelas copiadas à mão divergem. Por isso as fronteiras moram num único
arquivo de fixture versionado, `contrato/escada_resolucao.json`, lido pelos
testes dos dois lados. Divergência entre as implementações vira teste vermelho,
não um gráfico sutilmente errado.

### A.2 O buraco de materialização (pré-existente)

Medido na base que está rodando, em 2026-08-05:

```
view_name              | materialized_only |  max(bucket)         | max(sensor_reading.time)
sensor_reading_daily   | t                 | 2026-07-26 00:00Z    | 2026-08-05 20:00Z
sensor_reading_hourly  | t                 | 2026-08-05 17:00Z    | 2026-08-05 20:00Z
```

`materialized_only = true` (default do TimescaleDB desde a 2.13) significa que
a consulta **só enxerga o que já foi materializado**. O agregado diário está 10
dias atrás do bruto; o horário, 3 horas.

Isto já é um bug hoje, não uma consequência da tela nova: `?window=30d` lê
`sensor_reading_daily` e perde os últimos 10 dias. O dashboard disfarça porque
o `TimeseriesWidget` cola `useLiveTail` por cima — e o próprio
`chartOption.ts` documenta ter apanhado exatamente disto ("agregado 30d ainda
nao materializado").

`/analise` não tem cauda ao vivo por decisão de escopo. Sem tratar isto, o
usuário dá zoom na última hora, o gráfico simplesmente para no meio e nada
explica por quê.

**Correção: agregação em tempo real** (`materialized_only = false`) nas três
views. O Timescale passa a unir o que está materializado com o que falta,
calculado do bruto na hora. Custo: a consulta da borda mais recente fica mais
cara; irrelevante no volume atual e ainda barata depois, porque a parte pesada
continua vindo do materializado.

### A.3 Mudança de schema

Em `timescale/init.sql` **e** num script de migração aplicável à base que já
roda (o `init.sql` só executa em volume novo; sem o script, a base atual fica
com o schema velho).

Só o que precisa mudar muda — cada `DROP MATERIALIZED VIEW` é uma janela em que
o `/historico?window=` da stack de produção devolve vazio:

| View | Ação | Destrutivo? |
|---|---|---|
| `sensor_reading_hourly` | `ALTER … SET (timescaledb.materialized_only = false)` | Não. Nada é recriado; nenhum rollup lê desta view, então não precisa de `valor_count`. |
| `sensor_reading_daily` | Recriar com `count(*) AS valor_count` e `materialized_only = false`; política de refresh recriada junto | Sim. É a única view derrubada. Durante a migração, `?window=30d` devolve vazio. |
| `sensor_reading_minutely` | Criar nova, com `valor_count` e `materialized_only = false` | Não — não existe ainda. |

A re-materialização do diário parte de `sensor_reading`, que não é tocado — a
regra de que dado coletado nunca é apagado vale integralmente. Com 28 linhas no
diário e 370k no bruto, é questão de segundos.

`valor_count` só faz sentido no diário, porque é dele que semana e mês são
derivados (A.4). O horário não roda rollup nenhum, então não paga o preço de
ser recriado.

Se o `ALTER … SET (materialized_only = false)` não for aceito nesta versão do
TimescaleDB, o fallback é uma regra explícita no backend: qualquer span cujo
`ate` alcance a borda não materializada cai para `raw` naquele trecho. A
migração deve verificar isso antes de seguir, não assumir.

### A.4 Rollup de semana e mês

Derivados de `sensor_reading_daily`, não do bruto. `time_bucket` com intervalo
de mês sobre `timestamptz` foi verificado nesta base (TimescaleDB 2.28.3):

```sql
SELECT time_bucket(INTERVAL '7 days', bucket) AS b,
       min(valor_min), max(valor_max),
       sum(valor_avg * valor_count) / nullif(sum(valor_count), 0),
       sum(valor_count)
FROM sensor_reading_daily
WHERE sensor_id = %s AND bucket >= %s AND bucket < %s
GROUP BY b ORDER BY b
```

Mês idem, com `INTERVAL '1 month'`.

### A.5 Endpoint

`/sensores/{code}/historico` ganha parâmetros sem quebrar quem já usa:

```
GET /sensores/{code}/historico?window=24h                      ← inalterado (widgets do dashboard)
GET /sensores/{code}/historico?desde=<ISO>&ate=<ISO>&bucket=auto
→ { sensor_code, desde, ate, bucket: "minuto", resolution: "agg",
    points: [{ ts, min, max, avg, count }] }
```

- `bucket`: `auto` (default) resolve pelo span conforme A.1; `raw`, `minuto`,
  `hora`, `dia`, `semana`, `mes` forçam o degrau.
- `resolution` continua `raw` ou `agg`; com `raw`, os pontos são `{ ts, value }`.
- `desde` e `ate` são ISO 8601 **com timezone** (`2026-07-29T03:00:00Z`).
  Datetime sem offset é 400 — data sem fuso num sistema que roda em
  `America/Sao_Paulo` e grava em UTC é erro esperando acontecer.
- `window` e `desde/ate` são **mutuamente exclusivos**: mandar os dois é 400.
  Dois donos do mesmo recorte é ambiguidade que vira bug silencioso.
- `desde > ate`, ISO inválida ou bucket desconhecido → 400.
- Um bucket forçado que produziria mais que `MAX_PONTOS` (default 20000) →
  400 com o bucket sugerido no corpo, para o frontend avisar em vez de travar o
  browser.

Os dois tetos são coisas diferentes e ambos existem de propósito: `auto` mira
~2000 pontos por série (legibilidade), enquanto `MAX_PONTOS` = 20000 é o teto
de segurança de quem forçou o degrau na mão. Entre 2000 e 20000 o pedido é
atendido sem reclamar — é o usuário sabendo o que quer.

**Isolamento por site.** O guard de `buscar_agregado` (confere o `site_id` do
sensor contra `sites_permitidos`) vale para todas as consultas novas, inclusive
os rollups de semana e mês e a CAgg de minuto. Esta API já vazou dado entre
clientes uma vez; nenhuma consulta nova entra sem esse guard.

## Parte B — Frontend

### B.1 Arquivos

Rota nova dentro do `AuthGuard`, ao lado de `/`. Nada existente é reescrito.

| Arquivo | Papel |
|---|---|
| `pages/AnalisePage.tsx` | Layout, seleção, estado na URL |
| `components/MultiSeriesChart.tsx` | Irmão do `TimeSeriesChart`: N séries, dois eixos |
| `components/multiChartOption.ts` | Irmão do `chartOption.ts` |
| `lib/escolherBucket.ts` | `span → bucket`, pura, espelha A.1 |
| `lib/useSensoresDaArea.ts` | Deriva a lista da área a partir de `useSensors()` |

`chartOption.ts` **não** é generalizado. Ele carrega markArea de fora-limite,
gaps offline, faixa de silêncio e merge da cauda ao vivo — tudo escrito para
uma série. Estender no lugar transformaria `TimeSeriesChart.test.tsx` em
regressão; o irmão novo é mais barato e mais honesto.

### B.2 Seleção

`AreaSelect` (existente) escolhe a área. Abaixo, um `SearchSelect` multi
alimentado apenas com os sensores daquela área — o componente genérico já
aceita `items`, então `SensorSelect` não muda.

Trocar de área limpa a seleção de sensores.

**Regra das duas unidades.** Os selecionados são agrupados por
`SensorMeta.unidade`. A primeira unidade ocupa o eixo Y esquerdo, a segunda o
direito. Um sensor cuja unidade seria a terceira aparece desabilitado na lista,
com a mensagem: *"O gráfico comporta duas unidades — hoje bar e °C. Remova um
sensor para incluir umidade (%UR)."* O bloqueio é na entrada, não um erro
depois da seleção.

### B.3 Navegação no tempo

`dataZoom` do ECharts (roda do mouse dentro do gráfico + barra inferior), com
debounce de 300 ms. Ao estabilizar, o intervalo visível vira `[desde, ate]`,
`escolherBucket(span)` decide o degrau, e o TanStack Query busca com a chave
`['historico', sensorCode, bucket, desde, ate]`.

Chave por degrau é o que faz voltar ao zoom anterior ser instantâneo: vem do
cache, sem rede.

Barra de degraus **Auto · Minuto · Hora · Dia · Semana · Mês**, com `Auto` como
default.

### B.4 Desenho

- Linha do `avg` por série, sempre.
- Faixa translúcida `mín–máx` na mesma cor da série. Ligada por padrão com até
  2 sensores, desligada acima disso, sempre com toggle visível. Com 5 séries a
  faixa vira sopa visual.
- Cada série mapeada ao eixo (`yAxisIndex` 0 ou 1) pela sua unidade.
- Legenda com nome e unidade; clicar isola a série.
- `connectNulls: false`: bucket sem dado é buraco, não reta ligando os dois
  lados como se houvesse medição.

### B.5 Estado na URL

`/analise?area=AREA-EXPURGO&sensores=SNR-A,SNR-B&desde=<ISO>&ate=<ISO>&bucket=auto`

Recarregar preserva o estado e o link é compartilhável — metade do valor de uma
tela de análise é mandar "olha isto aqui" para outra pessoa.

### B.6 Entrada

- Link **Análise** na `Topbar`.
- Botão **Analisar histórico** no `SensorDetailDrawer`, que abre a página com a
  área e o sensor já preenchidos. É o caminho natural: estou olhando um sensor,
  quero comparar com os vizinhos.

## Casos de borda

| Situação | Comportamento |
|---|---|
| Zoom além do dado existente | Empty-state por série; o eixo mantém o intervalo pedido |
| Arrastar o zoom rapidamente | Debounce + cancelamento do TanStack; só a última janela busca |
| Sensor sem leitura no intervalo | Série vazia na legenda, as outras seguem normais |
| Área com um sensor só | Funciona; sobreposição não é obrigatória |
| Bucket forçado com span enorme | 400 do backend com bucket sugerido → aviso no frontend |
| Nenhum sensor selecionado | Gráfico vazio com instrução, sem requisição |
| Área sem nenhum sensor | Seletor vazio com mensagem |

## Testes

**Backend** (`api/tests/`):

- `escolher_bucket(span)` nas fronteiras exatas de cada degrau (3 h, 36 h, 90 d,
  5 anos, 20 anos), inclusive nos dois lados de cada uma.
- Rollup de semana e mês: caso montado à mão com dias de contagens diferentes,
  provando que a média é ponderada e não a média das médias.
- `window` e `desde/ate` juntos → 400; `desde > ate` → 400; bucket desconhecido
  → 400.
- Bucket forçado acima de `MAX_PONTOS` → 400 com sugestão.
- Guard de site em cada consulta nova: sensor de site não permitido devolve
  vazio, incluindo nos rollups.
- Regressão: `?window=24h` responde exatamente como antes.

**Migração** (`ingestao/tests/` ou script dedicado):

- Depois da migração, `valor_count` do diário bate com a contagem no bruto para
  o mesmo bucket.
- As três views reportam `materialized_only = false` em
  `timescaledb_information.continuous_aggregates`.
- **Sem buraco de borda:** para cada view, o bucket mais recente devolvido pela
  consulta cobre o `max(time)` do bruto. É o teste que prova que o problema
  medido em A.2 foi corrigido, e ele falharia hoje.

**Frontend** (`frontend/src/`):

- `escolherBucket` nas mesmas fronteiras do backend — as duas tabelas não podem
  divergir.
- `multiChartOption`: dois `yAxis` quando há duas unidades, um quando há uma;
  cada série no `yAxisIndex` certo; faixa mín–máx só quando ligada;
  `connectNulls: false`.
- `AnalisePage`: terceira unidade bloqueada com a mensagem certa; troca de área
  limpa a seleção; URL espelha o estado; zoom dispara busca com o bucket novo;
  nenhum sensor selecionado não dispara requisição.

## Dois planos de implementação

A fronteira A/B desta spec é também a fronteira de entrega. Cada metade vira um
plano próprio; a primeira produz software funcionando e testável por `curl`
sem depender da segunda.

**Plano A — backend**

1. Migração de schema: `ALTER` no horário, recriação do diário com
   `valor_count`, criação do minutely, todas com `materialized_only = false`;
   mais o teste de ausência de buraco de borda.
2. `escolher_bucket` lendo `contrato/escada_resolucao.json`.
3. Consultas novas em `api/timescale.py` (minutely e rollups), com o guard de
   site em cada uma.
4. Endpoint `/historico` com `desde/ate/bucket`, mantendo `window` intacto.

**Plano B — frontend** (consome o contrato do Plano A)

5. `escolherBucket` contra a mesma fixture + `multiChartOption` — puros,
   testáveis sem DOM.
6. `MultiSeriesChart`.
7. `AnalisePage` com seleção, regra das duas unidades e estado na URL.
8. Zoom ligado à busca.
9. Entradas: Topbar e `SensorDetailDrawer`.
10. Verificação visual no browser contra a stack real, com dados de verdade.
