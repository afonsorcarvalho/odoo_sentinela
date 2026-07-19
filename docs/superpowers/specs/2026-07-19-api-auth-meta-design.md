# Design — Fase 3: Auth/JWT + API de Meta (`sensores`)

> Complementa `frontend/CONTRACTS.md` (contrato de dados já congelado pelo frontend) e `diretrizes_projeto.md` §12 (Odoo como provedor de identidade, JWT). Abre a Fase 3 do roadmap — primeira fatia (auth + metadados), antes de histórico (Timescale) e tempo real (SSE).

## Escopo desta rodada

Um novo serviço FastAPI (`api/`) com: endpoint de login que valida credenciais Odoo e emite JWT; três endpoints de metadados de sensor (`listar`, `obter`, `threshold`) que servem exatamente os shapes já definidos em `frontend/CONTRACTS.md` (`SensorMeta`, `Threshold`), lendo do cadastro Odoo já existente (Fase 1).

**Fora de escopo**: filtragem multi-tenant por `partner_id` na API (o JWT carrega o claim, mas nada ainda filtra por ele — só há um usuário de teste, `admin`, que vê tudo; filtragem real fica para quando houver um segundo usuário/cliente pra provar o isolamento), usuário de serviço dedicado (continua `admin`/`admin`), API de histórico (Timescale), API de tempo real (SSE/MQTT).

## Decisões desta rodada

| Ponto | Decisão |
|---|---|
| Conexão com Odoo | Uma única conexão de serviço (`admin`/`admin`, via env vars), reaproveitando `ingestao.odoo_cliente` — a API **não** autentica no Odoo como o usuário logado; login só valida a credencial (via uma chamada descartável a `odoo_cliente.conectar`) e emite o JWT. |
| Biblioteca JWT | `PyJWT`, HS256, segredo via env var (`API_JWT_SECRET`), expiração 1h. |
| Reuso de `ingestao.odoo_cliente` | Autorizado — `api/` e `ingestao/` são dois componentes server-side do mesmo backend (diferente da fronteira real entre `ingestao` e `coletor_simulado`, que simula uma separação física firmware/servidor). |

## 1. Estrutura

```
api/
├── __init__.py
├── main.py       # app FastAPI, inclui routers, /health
├── odoo.py        # conexão de serviço (lru_cache) reaproveitando ingestao.odoo_cliente
├── auth.py         # POST /auth/login, emissão e verificação de JWT
├── meta.py          # GET /sensores, /sensores/{code}, /sensores/{code}/threshold
├── requirements.txt
└── tests/
    ├── __init__.py
    ├── test_auth.py
    └── test_meta.py
```

## 2. Conexão de serviço (`odoo.py`)

- `get_cliente_servico()` (com `functools.lru_cache`): conecta uma vez com credenciais de serviço (env vars `ODOO_URL`/`ODOO_DB`/`ODOO_USUARIO_SERVICO`/`ODOO_SENHA_SERVICO`, defaults `http://localhost:8189`/`sentinela`/`admin`/`admin`), reaproveitada em todas as requisições via `Depends`.

## 3. Autenticação (`auth.py`)

- `POST /auth/login` — body `{usuario, senha}`. Chama `odoo_cliente.conectar(url, db, usuario, senha)` só para validar (levanta `RuntimeError` → `401` se falhar). Em sucesso, busca `partner_id` do usuário via a conexão de serviço (`res.users.read`), emite JWT com claims `{sub: uid, partner_id, exp}`.
- `verificar_token` (dependency): decodifica e valida o JWT (assinatura + expiração) do header `Authorization: Bearer <token>`; `401` se inválido/expirado. Usado por todos os endpoints de `meta.py`.

## 4. Metadados de sensor (`meta.py`)

Shapes exatamente como `frontend/CONTRACTS.md`:
- `SensorMeta`: `sensor_code`, `name`, `unidade` (do sensor, ou `measurement_type.unidade_padrao` como fallback se em branco), `protocolo_origem` (valor já em minúsculo no Odoo — `4-20ma`/`rs485`/`i2c`, bate direto com o tipo TS), `measurement_type: {code, name}`, `area: {area_code, name, category}` (`category` = nome da `area.category`, achatado pra string conforme o contrato já documenta).
- `Threshold`: `sensor_id` (aqui é o **`sensor_code`**, não o id numérico do Odoo — é assim que o frontend usa a chave, conforme `mock/fixtures.ts`), `limite_min`, `limite_max`, `is_valor_padrao_regulatorio`.

Endpoints:
- `GET /sensores` → lista todos (sem filtro de tenant nesta rodada — inclui sensores dos dois cadastros existentes, `CMEOX-01` e `SITE-SIM-0001`).
- `GET /sensores/{sensor_code}` → `404` se não existir.
- `GET /sensores/{sensor_code}/threshold` → `404` se o sensor não existir; `null` (200, corpo `null`) se existir mas não tiver `alarm.threshold` configurado.

## 5. Testes

Contra o Odoo real já rodando (mesmo padrão de `ingestao/`), usando os dois cadastros existentes como fixture natural — `CMEOX-01`/`TEMP-01` (sem threshold configurado, prova o caminho `null`) e `SITE-SIM-0001`/sensores simulados (sem threshold também, já que `provisionar_odoo_sim` nunca criou nenhum) — se nenhum dos dois tiver threshold, o teste do caminho "com threshold" precisa criar um via `odoo_cliente` no setup e limpar depois.

- `test_auth.py`: login com `admin`/`admin` retorna token válido (decodificável, com `sub`/`partner_id`/`exp`); login com senha errada retorna `401`.
- `test_meta.py`: `/sensores` sem token → `401`; com token → `200` e a lista inclui os sensores conhecidos; `/sensores/{code}` para código conhecido bate o shape exato; para código inexistente → `404`; `/sensores/{code}/threshold` para sensor sem limiar → `200` com `null`; para sensor com limiar (criado no setup do teste) → `200` com os valores certos; para sensor inexistente → `404`.

## Pontos que seguem em aberto (não bloqueiam esta rodada)

- Filtragem multi-tenant real por `partner_id` na API — precisa de um segundo usuário/cliente de teste pra provar.
- Usuário de serviço dedicado (hoje `admin`/`admin`).
- API de histórico (Timescale) e API de tempo real (SSE) — próximas rodadas da Fase 3.
