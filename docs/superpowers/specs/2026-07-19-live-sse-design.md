# Feed ao vivo (LivePoint via SSE) — Design

## Contexto

`frontend/CONTRACTS.md` já especifica `LivePoint` (`sensor_code`, `ts`,
`value`, `alarm_state`) como "publicado via SSE (Server-Sent Events) ou
WebSocket feed em tempo real — NÃO é modelo Odoo". O frontend já consome
isso via `liveApi.subscribe(code, cb) -> unsubscribe`
(`frontend/src/lib/api/contracts.ts`), hoje só com `mockLiveApi`
(um `setInterval` sintético). `useLiveStatuses`/`useLiveTail` chamam
`subscribe` uma vez por `sensor_code` (Overview: um por sensor visível;
Sensor Detail: um só).

O backend (`api/`) já tem auth/JWT, meta de sensores e histórico
(TimescaleDB). A ingestão (`ingestao/`) é toda batch/arquivo: o coletor
simulado gera um dia inteiro de leituras (a cada 60s) num arquivo,
`ingestor.py` processa o arquivo de uma vez e termina — não existe hoje
nenhum processo contínuo capaz de empurrar eventos direto pras conexões
abertas na API. A fonte de verdade pro feed ao vivo só pode ser o
TimescaleDB sendo observado.

## Objetivo

Endpoint SSE `GET /sensores/{code}/live` publicando novos pontos de
`sensor_reading` assim que são gravados, mais o adapter `realLiveApi` no
frontend consumindo esse feed via `EventSource`.

## Arquitetura

```
Postgres trigger (AFTER INSERT sensor_reading)
  → pg_notify('sensor_reading_new', {sensor_id, time, valor})
  → API: task de background com asyncpg (LISTEN nesse canal)
  → registry em memória: dict[sensor_code] → set[asyncio.Queue]
  → GET /sensores/{code}/live?token=<jwt>  (SSE, StreamingResponse)
  → frontend: realLiveApi (EventSource) → computeStatus() local → LivePoint completo → cb()
```

**Decisões já validadas:**
- Transporte: SSE (não WebSocket, não polling) — one-way é tudo que
  `subscribe(code, cb)` precisa; `EventSource` nativo reconecta sozinho.
- Origem: Postgres LISTEN/NOTIFY via trigger no INSERT — desacoplado de
  quem grava (simulador batch hoje, hardware real depois), latência
  mínima.
- `alarm_state`: computado no frontend, não no backend. O wire só manda
  `{sensor_code, ts, value}`; o adapter já busca/cacheia o threshold via
  `realMetaApi.getThreshold` e roda `computeStatus()` (já existe, já
  testada em outras telas) — zero duplicação da regra de negócio
  (`WARN_MARGIN`, etc.) entre Python e TypeScript.
- Auth: token JWT via query string (`?token=`) — `EventSource` nativo do
  browser não manda header `Authorization`, então a validação do token
  nessa rota lê de query param em vez de header (endpoint novo e
  específico, sem afetar as rotas que já usam Bearer header).

## Backend

### Trigger SQL (migration nova em `ingestao/timescale.py` ou script de
schema equivalente ao que já criou `sensor_reading`)

```sql
CREATE OR REPLACE FUNCTION notify_sensor_reading() RETURNS trigger AS $$
BEGIN
  PERFORM pg_notify(
    'sensor_reading_new',
    json_build_object(
      'sensor_id', NEW.sensor_id,
      'time', extract(epoch from NEW.time) * 1000,
      'valor', NEW.valor
    )::text
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER sensor_reading_notify
  AFTER INSERT ON sensor_reading
  FOR EACH ROW EXECUTE FUNCTION notify_sensor_reading();
```

Canal único (`sensor_reading_new`), não um canal por sensor — LISTEN
dinâmico por sensor não escala e complica a gestão de conexão. Filtro por
`sensor_id` acontece em código, no listener.

### Listener (`api/live.py`, task de background)

- Usa `asyncpg` (dependência nova em `api/requirements.txt` — só ele tem
  `add_listener()` nativo pra asyncio; replicar isso com `psycopg2`
  exigiria thread dedicada + polling manual de socket, mais complexo sem
  necessidade).
- Iniciada no startup do FastAPI (`app.on_event('startup')` ou lifespan),
  mantém uma conexão `LISTEN sensor_reading_new`, callback recebe o
  payload, dá parse no JSON, publica na(s) `asyncio.Queue` registrada(s)
  pra aquele `sensor_id` no registry.
- Se a conexão cair: retry com backoff simples (ex.: espera fixa curta,
  tenta reconectar, loop infinito) — sem supervisor/alerta nessa fatia.

### Registry (`api/live.py`)

Estrutura em memória, `dict[str, set[asyncio.Queue]]` (`sensor_code ->
queues`). Duas operações: `registrar(sensor_code) -> Queue` (cria e
adiciona) e `remover(sensor_code, queue)` (limpa no disconnect do
cliente). Vive só no processo — reinício da API perde as inscrições
ativas (aceitável: cliente reconecta o `EventSource` e reabre).

### Endpoint (`api/live.py`)

```
GET /sensores/{sensor_code}/live?token=<jwt>
```

- Dependency nova de auth (`verificar_token_query`) — reaproveita a
  mesma lógica de decode/secret de `api/auth.py`, só muda de onde lê o
  token (query param em vez de header `Authorization`).
- 404 se sensor não existe (`obter_sensor`, mesmo padrão de
  `api/historico.py`).
- `StreamingResponse(media_type='text/event-stream')`: registra uma
  queue no registry, faz um loop assíncrono consumindo a queue e
  formatando cada item como `data: {json}\n\n`; no `finally` (cliente
  desconectou), remove a queue do registry.

## Frontend

`frontend/src/lib/api/real/liveApi.ts`:

```ts
export const realLiveApi: LiveApi = {
  subscribe(sensor_code, cb) {
    let threshold: Threshold | null = null
    realMetaApi.getThreshold(sensor_code).then((t) => { threshold = t })

    const token = localStorage.getItem(TOKEN_STORAGE_KEY)
    const es = new EventSource(`${BASE_URL}/sensores/${sensor_code}/live?token=${token}`)
    es.onmessage = (event) => {
      const { sensor_id, time, valor } = JSON.parse(event.data)
      const { state } = computeStatus(valor, threshold)
      const alarm_state = state === 'unknown' ? 'ok' : state
      cb({ sensor_code, ts: time, value: valor, alarm_state })
    }
    return () => es.close()
  },
}
```

(Assinaturas exatas de campo — `sensor_id`/`time`/`valor` no wire vs.
`sensor_code`/`ts`/`value` no `LivePoint` — serão fechadas no plano de
implementação, não são um detalhe de design em aberto: o wire usa os
nomes de coluna do Postgres, o `LivePoint` usa os nomes do contrato
TypeScript.)

`index.ts`: `liveApi` passa a entrar no mesmo switch `VITE_API_MODE` que
já cobre `auth`/`meta`/`history`.

**Reconexão:** `EventSource` nativo já reconecta sozinho por conta
própria — sem replay/backfill do que foi perdido durante a
desconexão. Isso é papel do `/historico`, não desse feed.

## Erros / edge cases

- Token ausente/inválido na query → 401 antes de abrir o stream.
- Sensor inexistente → 404 antes de abrir o stream.
- Cliente desconecta → queue removida do registry (sem vazamento de
  memória).
- Listener perde conexão com Postgres → retry com backoff simples, log —
  sem alerta/supervisor nessa fatia.

## Testes

- **Trigger dispara NOTIFY:** teste de integração com uma conexão
  `psycopg2` fazendo `LISTEN sensor_reading_new` + `select()` com
  timeout no socket da conexão, insere uma linha em `sensor_reading`,
  confirma que a notificação chega com o payload esperado.
- **Registry:** unit test puro — registra queue, publica, item chega;
  remove, não chega mais nada pra aquela queue.
- **Endpoint:** `TestClient` consumindo o `StreamingResponse` —
  401 sem token, 401 token inválido, 404 sensor inexistente, round-trip
  publicando direto no registry (sem depender do trigger real rodando
  no teste do endpoint — separa a preocupação "o endpoint entrega o que
  tá na queue" de "o trigger enche a queue certo").
- **Frontend:** mock do `EventSource` global (jsdom não tem um nativo) —
  testa a URL montada (sensor code + token), `onmessage` computando
  `alarm_state` certo a partir do threshold cacheado, `unsubscribe`
  fechando a conexão (`es.close()` chamado).

## Fora de escopo

- Multiplexar N `subscribe()` numa única conexão HTTP (hoje Overview
  abre 1 `EventSource` por sensor visível — aceitável pra poucos
  sensores; otimização futura se o número crescer).
- Supervisor/alerta se o listener de background cair e ficar preso em
  retry.
- Ticket de curta duração pra auth (token direto via query já decidido
  como suficiente pra esse projeto).
- Confirmação/ack de entrega — se o cliente estava desconectado quando
  um ponto foi publicado, ele simplesmente não chega (sem buffer/replay
  por sensor).
