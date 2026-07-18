# Design — Fase 3: API de Histórico (TimescaleDB)

> Complementa `docs/superpowers/specs/2026-07-19-api-auth-meta-design.md` (auth+meta, rodada anterior) e `frontend/CONTRACTS.md` (`HistoryResponse`). Segunda fatia da Fase 3 — tempo real (SSE) fica para a rodada seguinte.

## Escopo desta rodada

Um endpoint `GET /sensores/{sensor_code}/historico?window=...` no serviço `api/` que lê do TimescaleDB (raw ou agregado, conforme a janela) e serve exatamente o shape `HistoryResponse` já congelado em `frontend/CONTRACTS.md`.

**Fora de escopo**: tempo real (SSE/MQTT) — próxima rodada; filtragem multi-tenant (mesma decisão já registrada na rodada de auth+meta).

## Fato de arquitetura confirmado nesta rodada

`sensor_reading.sensor_id` no TimescaleDB já armazena o **`sensor_code`** (string) diretamente — não é o id numérico do Odoo (confirmado lendo `ingestao/timescale.py::inserir_leituras`, que grava `leitura['sensor_id']`, vindo do parsing do arquivo). A API de histórico consulta o Timescale diretamente pelo `sensor_code`, sem tradução via Odoo — só usa o Odoo pra confirmar que o sensor existe (`404` se não).

## 1. Mapeamento janela → resolução → fonte

| `window` | `resolution` | Tabela |
|---|---|---|
| `1h` | `raw` | `sensor_reading` |
| `24h` | `agg` | `sensor_reading_hourly` |
| `7d` | `agg` | `sensor_reading_hourly` |
| `30d` | `agg` | `sensor_reading_daily` |

## 2. Consultas (`api/timescale.py`)

- Reaproveita `ingestao.timescale.conectar` (mesmo padrão de reuso de `api/odoo.py` sobre `ingestao.odoo_cliente`).
- `buscar_raw(conn, sensor_code, desde) -> list[dict]`: `SELECT time, valor FROM sensor_reading WHERE sensor_id = %s AND time >= %s ORDER BY time`.
- `buscar_agregado(conn, sensor_code, tabela, desde) -> list[dict]`: `SELECT bucket, valor_min, valor_max, valor_avg FROM {tabela} WHERE sensor_id = %s AND bucket >= %s ORDER BY bucket` (`tabela` é `sensor_reading_hourly` ou `sensor_reading_daily`, nome de tabela vem de uma constante interna, nunca de input do usuário — sem risco de injeção).

## 3. Endpoint (`api/historico.py`)

`GET /sensores/{sensor_code}/historico?window=1h|24h|7d|30d` — exige JWT (`verificar_token`, reaproveitado de `api/auth.py`). Fluxo: confirma que o sensor existe via `meta.obter_sensor` (reaproveitado de `api/meta.py`) → `404` se não; resolve janela → resolução/tabela/`desde` (`now() - intervalo da janela`); consulta; monta `HistoryResponse`:
- `sensor_code`, `window` (ecoa o parâmetro), `resolution` (`raw`/`agg`), `points` (lista de `{ts, value}` ou `{ts, min, max, avg}`, `ts` em milissegundos).

## 4. Testes

Como os dados simulados das rodadas anteriores já foram limpos, os testes inserem linhas direto no Timescale (via `ingestao.timescale.inserir_leituras` ou SQL direto) com timestamps **relativos a `now()`** (não datas fixas simuladas) — só assim uma janela relativa ao presente encontra alguma coisa. Limpeza no `finally`, mesmo padrão das rodadas anteriores.

- `window=1h` com leituras recentes inseridas → `resolution='raw'`, pontos batem com os valores inseridos.
- `window=24h`/`30d` — como os continuous aggregates do Timescale têm política de refresh com atraso (`start_offset`), inserir e esperar o aggregate materializar não é confiável num teste rápido; o teste chama `refresh_continuous_aggregate` diretamente via SQL pra forçar a materialização antes de consultar (comando administrativo do Timescale, não faz parte do fluxo de produção).
- `sensor_code` inexistente no Odoo → `404`.
- `window` inválido (fora do enum) → `422` (validação do FastAPI via `Literal`/enum no parâmetro).

## Pontos que seguem em aberto (não bloqueiam esta rodada)

- Tempo real (SSE) — próxima rodada, fecha a Fase 3.
- Filtragem multi-tenant — mesma pendência da rodada de auth+meta.
