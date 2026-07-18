# Feed ao vivo (backend: trigger + listener + endpoint SSE) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend completo do feed ao vivo — trigger Postgres que dispara `NOTIFY` no INSERT de `sensor_reading`, listener `asyncpg` em background que republica pra um registry em memória, e `GET /sensores/{sensor_code}/live?token=<jwt>` (SSE) servindo esse registry. O adapter frontend (`realLiveApi`) é uma fatia separada, depois desta.

**Architecture:** `timescale/init.sql` (trigger SQL) → `api/live_listener.py` (`escutar()`, conexão `asyncpg` dedicada com `LISTEN`, reconecta em loop) → `api/live.py` (registry em memória `dict[sensor_code, set[Queue]]` + endpoint `StreamingResponse`) → `api/main.py` (monta o router, inicia o listener no startup).

**Tech Stack:** FastAPI (já em uso), `asyncpg` (novo — só ele tem `add_listener()` nativo pra asyncio; `psycopg2` já usado no resto do projeto exigiria thread+polling manual pra LISTEN/NOTIFY), `psycopg2` (testes, reaproveitando `ingestao.timescale.conectar`), TimescaleDB já rodando (`localhost:5433`, container `odoo_sentinela-timescaledb-1`).

## Global Constraints

- Canal `NOTIFY` único: `sensor_reading_new` — não um canal por sensor. Filtro por `sensor_id` acontece em código (no listener), não no Postgres.
- Payload do `NOTIFY`: `{"sensor_id": <sensor_code>, "time": <ms unix>, "valor": <float>}`.
- Wire do SSE (o que o endpoint manda pro cliente): mesmo shape do payload do `NOTIFY`, sem `alarm_state` — isso é responsabilidade do frontend (fatia separada, fora deste plano).
- Auth do endpoint SSE via query param `?token=<jwt>` (não header `Authorization` — `EventSource` nativo do browser não manda headers customizados). Reaproveita `SECRET`/`ALGORITHM` já definidos em `api/auth.py`.
- 404 se o sensor não existe, checado ANTES de abrir o stream (mesmo padrão de `api/historico.py`).
- `DSN` (TimescaleDB) lido de `os.environ.get('TIMESCALE_DSN', 'postgresql://sentinela:sentinela@localhost:5433/sentinela')` — mesmo padrão já estabelecido em `api/historico.py`.
- Registry em memória assume processo único / single event loop (sem lock — dict/set mutados só dentro do loop async da própria API). Deploy multi-worker não é suportado por este design; fora de escopo.
- `timescale/init.sql` só roda automaticamente em volume novo do container (`docker-entrypoint-initdb.d`). Como o volume já existe com dados, toda alteração de schema desta fatia precisa ser aplicada manualmente na instância rodando (`docker exec ... psql`), além de ser adicionada ao `init.sql` (fonte de verdade pra setups futuros).
- Sem supervisor/alerta se o listener de background cair e ficar em retry — fora de escopo.

---

## Task 1: Trigger SQL (`sensor_reading_notify`)

**Files:**
- Modify: `timescale/init.sql` (append no final)
- Test: `api/tests/test_live_trigger.py`

**Interfaces:**
- Consumes: `ingestao.timescale.conectar(dsn) -> connection` (só pra inserir/limpar linha de teste).
- Produces: canal Postgres `sensor_reading_new`, disparado a cada INSERT em `sensor_reading`, payload JSON `{"sensor_id", "time", "valor"}` — consumido pela Task 3 (listener).

- [ ] **Step 1: Escrever o teste em `api/tests/test_live_trigger.py`**

```python
import json
import select
from datetime import datetime, timezone

import psycopg2

from ingestao.timescale import conectar

DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'
SENSOR_CODE_TESTE = 'SNR-LIVE-TRIGGER-TEST-01'


def _limpar():
    conn = conectar(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sensor_reading WHERE sensor_id = %s", (SENSOR_CODE_TESTE,))
        conn.commit()
    finally:
        conn.close()


def test_trigger_dispara_notify_no_insert():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    _limpar()
    try:
        with conn.cursor() as cur:
            cur.execute("LISTEN sensor_reading_new;")

        conn_insert = conectar(DSN)
        try:
            agora = datetime.now(timezone.utc)
            with conn_insert.cursor() as cur:
                cur.execute(
                    "INSERT INTO sensor_reading "
                    "(time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        agora, 'SITE-TEST', 'COL-TEST', SENSOR_CODE_TESTE,
                        'AREA-TEST', 'temperatura', 23.4, 'C', '4-20ma', 'ok',
                    ),
                )
            conn_insert.commit()
        finally:
            conn_insert.close()

        prontos = select.select([conn], [], [], 3)
        assert prontos[0], "nenhuma notificacao recebida em 3s — trigger nao disparou?"
        conn.poll()
        assert conn.notifies, "select() retornou mas conn.notifies esta vazio"
        notificacao = conn.notifies.pop(0)
        assert notificacao.channel == 'sensor_reading_new'
        payload = json.loads(notificacao.payload)
        assert payload['sensor_id'] == SENSOR_CODE_TESTE
        assert payload['valor'] == 23.4
    finally:
        _limpar()
        conn.close()
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run (a partir da raiz do repo): `python3 -m pytest api/tests/test_live_trigger.py -v`
Expected: falha no `assert prontos[0]` — timeout de 3s sem notificação, porque o trigger ainda não existe (o INSERT acontece normal, mas nada dispara `NOTIFY`).

- [ ] **Step 3: Adicionar o trigger em `timescale/init.sql`**

Acrescentar ao final do arquivo:

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

DROP TRIGGER IF EXISTS sensor_reading_notify ON sensor_reading;
CREATE TRIGGER sensor_reading_notify
    AFTER INSERT ON sensor_reading
    FOR EACH ROW EXECUTE FUNCTION notify_sensor_reading();
```

- [ ] **Step 4: Aplicar o mesmo SQL na instância do TimescaleDB já rodando**

Run:
```bash
docker exec -i odoo_sentinela-timescaledb-1 psql -U sentinela -d sentinela <<'EOF'
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

DROP TRIGGER IF EXISTS sensor_reading_notify ON sensor_reading;
CREATE TRIGGER sensor_reading_notify
    AFTER INSERT ON sensor_reading
    FOR EACH ROW EXECUTE FUNCTION notify_sensor_reading();
EOF
```
Expected: `CREATE FUNCTION`, `DROP TRIGGER` (ou aviso de que não existia), `CREATE TRIGGER` — sem erro.

- [ ] **Step 5: Rodar o teste e confirmar que passa**

Run: `python3 -m pytest api/tests/test_live_trigger.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add timescale/init.sql api/tests/test_live_trigger.py
git commit -m "feat: trigger Postgres NOTIFY no insert de sensor_reading"
```

---

## Task 2: Registry em memória (`api/live.py`)

**Files:**
- Create: `api/live.py`
- Test: `api/tests/test_live_registry.py`

**Interfaces:**
- Consumes: nada de tasks anteriores.
- Produces: `registrar(sensor_code: str) -> asyncio.Queue`, `remover(sensor_code: str, fila: asyncio.Queue) -> None`, `publicar(sensor_code: str, payload: dict) -> None` — usados pela Task 3 (`publicar`) e Task 4 (`registrar`/`remover` no endpoint).

- [ ] **Step 1: Escrever o teste em `api/tests/test_live_registry.py`**

```python
import asyncio

import pytest

from api import live


def test_registrar_e_publicar_entrega_na_fila():
    async def cenario():
        fila = live.registrar('SNR-1')
        live.publicar('SNR-1', {'valor': 1})
        item = await asyncio.wait_for(fila.get(), timeout=1)
        assert item == {'valor': 1}
        live.remover('SNR-1', fila)

    asyncio.run(cenario())


def test_publicar_sem_inscritos_nao_lanca_erro():
    live.publicar('SNR-SEM-INSCRITOS', {'valor': 2})


def test_remover_impede_entrega_futura():
    async def cenario():
        fila = live.registrar('SNR-2')
        live.remover('SNR-2', fila)
        live.publicar('SNR-2', {'valor': 3})
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(fila.get(), timeout=0.2)

    asyncio.run(cenario())
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python3 -m pytest api/tests/test_live_registry.py -v`
Expected: `ModuleNotFoundError: No module named 'api.live'`.

- [ ] **Step 3: Criar `api/live.py`**

```python
import asyncio

_registry: dict[str, set[asyncio.Queue]] = {}


def registrar(sensor_code: str) -> asyncio.Queue:
    fila = asyncio.Queue()
    _registry.setdefault(sensor_code, set()).add(fila)
    return fila


def remover(sensor_code: str, fila: asyncio.Queue) -> None:
    filas = _registry.get(sensor_code)
    if filas is None:
        return
    filas.discard(fila)
    if not filas:
        _registry.pop(sensor_code, None)


def publicar(sensor_code: str, payload: dict) -> None:
    for fila in _registry.get(sensor_code, ()):
        fila.put_nowait(payload)
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `python3 -m pytest api/tests/test_live_registry.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add api/live.py api/tests/test_live_registry.py
git commit -m "feat: registry em memoria pro feed ao vivo (registrar/remover/publicar)"
```

---

## Task 3: Listener `asyncpg` (`api/live_listener.py`)

**Files:**
- Create: `api/live_listener.py`
- Test: `api/tests/test_live_listener.py`
- Modify: `api/requirements.txt`

**Interfaces:**
- Consumes: `api.live.publicar(sensor_code, payload)` (Task 2); canal `sensor_reading_new` (Task 1).
- Produces: `escutar(dsn=DSN) -> None` (coroutine infinita, cancelável) — usado pela Task 4 no startup do FastAPI.

- [ ] **Step 1: Adicionar `asyncpg` como dependência**

Modificar `api/requirements.txt`, acrescentando a linha:
```
asyncpg>=0.29
```

Instalar: `pip install asyncpg>=0.29`

- [ ] **Step 2: Escrever o teste em `api/tests/test_live_listener.py`**

```python
import asyncio
from datetime import datetime, timezone

from api import live, live_listener
from ingestao.timescale import conectar

DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'
SENSOR_CODE_TESTE = 'SNR-LIVE-LISTENER-TEST-01'


def _limpar():
    conn = conectar(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sensor_reading WHERE sensor_id = %s", (SENSOR_CODE_TESTE,))
        conn.commit()
    finally:
        conn.close()


def test_escutar_publica_no_registry_quando_trigger_dispara():
    async def cenario():
        _limpar()
        fila = live.registrar(SENSOR_CODE_TESTE)
        task = asyncio.create_task(live_listener.escutar())
        try:
            await asyncio.sleep(0.5)  # da tempo do listener conectar e comecar a escutar

            conn = conectar(DSN)
            try:
                agora = datetime.now(timezone.utc)
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO sensor_reading "
                        "(time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            agora, 'SITE-TEST', 'COL-TEST', SENSOR_CODE_TESTE,
                            'AREA-TEST', 'temperatura', 18.2, 'C', '4-20ma', 'ok',
                        ),
                    )
                conn.commit()
            finally:
                conn.close()

            item = await asyncio.wait_for(fila.get(), timeout=3)
            assert item['sensor_id'] == SENSOR_CODE_TESTE
            assert item['valor'] == 18.2
        finally:
            task.cancel()
            live.remover(SENSOR_CODE_TESTE, fila)
            _limpar()

    asyncio.run(cenario())
```

- [ ] **Step 3: Rodar o teste e confirmar que falha**

Run: `python3 -m pytest api/tests/test_live_listener.py -v`
Expected: `ModuleNotFoundError: No module named 'api.live_listener'`.

- [ ] **Step 4: Criar `api/live_listener.py`**

```python
import asyncio
import json
import os

import asyncpg

from . import live

DSN = os.environ.get('TIMESCALE_DSN', 'postgresql://sentinela:sentinela@localhost:5433/sentinela')
CANAL = 'sensor_reading_new'
RETRY_SEGUNDOS = 2


def _receber_notificacao(connection, pid, channel, payload):
    dados = json.loads(payload)
    live.publicar(dados['sensor_id'], dados)


async def escutar(dsn=DSN):
    while True:
        try:
            conn = await asyncpg.connect(dsn)
            try:
                await conn.add_listener(CANAL, _receber_notificacao)
                while True:
                    await asyncio.sleep(3600)
            finally:
                await conn.close()
        except (OSError, asyncpg.PostgresError):
            await asyncio.sleep(RETRY_SEGUNDOS)
```

- [ ] **Step 5: Rodar o teste e confirmar que passa**

Run: `python3 -m pytest api/tests/test_live_listener.py -v`
Expected: 1 passed. (Se falhar por timeout aguardando o item na fila, confirme que a Task 1 foi mesmo aplicada na instância rodando — Step 4 daquela task.)

- [ ] **Step 6: Commit**

```bash
git add api/live_listener.py api/tests/test_live_listener.py api/requirements.txt
git commit -m "feat: listener asyncpg escutando NOTIFY e republicando no registry"
```

---

## Task 4: Endpoint SSE + auth por query token + wiring + verificação final

**Files:**
- Modify: `api/auth.py`
- Modify: `api/live.py`
- Modify: `api/main.py`
- Test: `api/tests/test_live_endpoint.py`

**Interfaces:**
- Consumes: `api.live.registrar`/`remover`/`publicar` (Task 2); `api.live_listener.escutar` (Task 3); `api.meta.obter_sensor`; `api.odoo.get_cliente_servico`; `SECRET`/`ALGORITHM` já existentes em `api.auth`.
- Produces: `verificar_token_query(token: str) -> dict` (dependency FastAPI); rota `GET /sensores/{sensor_code}/live` montada em `api.main.app`.

- [ ] **Step 1: Escrever o teste em `api/tests/test_live_endpoint.py`**

```python
import asyncio
import json

import httpx
from fastapi.testclient import TestClient

from api import live
from api.main import app

SENSOR_CODE = 'SNR-SIM-TEMP-01'


def _obter_token():
    client = TestClient(app)
    resposta = client.post('/auth/login', json={'usuario': 'admin', 'senha': 'admin'})
    return resposta.json()['access_token']


def test_live_sem_token_retorna_422():
    client = TestClient(app)
    resposta = client.get(f'/sensores/{SENSOR_CODE}/live')
    assert resposta.status_code == 422


def test_live_token_invalido_retorna_401():
    client = TestClient(app)
    resposta = client.get(f'/sensores/{SENSOR_CODE}/live', params={'token': 'lixo.invalido.aqui'})
    assert resposta.status_code == 401


def test_live_sensor_inexistente_retorna_404():
    client = TestClient(app)
    token = _obter_token()
    resposta = client.get('/sensores/SNR-NAO-EXISTE-XYZ/live', params={'token': token})
    assert resposta.status_code == 404


def test_live_recebe_ponto_publicado_no_registry():
    token = _obter_token()

    async def cenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
            async with client.stream(
                'GET', f'/sensores/{SENSOR_CODE}/live', params={'token': token},
            ) as resposta:
                assert resposta.status_code == 200
                await asyncio.sleep(0.2)  # da tempo do endpoint registrar a fila antes de publicar
                live.publicar(SENSOR_CODE, {'sensor_id': SENSOR_CODE, 'time': 1700000000000, 'valor': 25.0})
                async for linha in resposta.aiter_lines():
                    if linha.startswith('data: '):
                        payload = json.loads(linha[len('data: '):])
                        assert payload['valor'] == 25.0
                        break

    asyncio.run(cenario())
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python3 -m pytest api/tests/test_live_endpoint.py -v`
Expected: `404` genérico do FastAPI pra todos os casos (rota `/sensores/{code}/live` ainda não existe).

- [ ] **Step 3: Adicionar `verificar_token_query` em `api/auth.py`**

Acrescentar ao final do arquivo (depois de `verificar_token`):

```python


def verificar_token_query(token: str):
    try:
        return jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail='token inválido ou expirado')
```

- [ ] **Step 4: Adicionar o endpoint em `api/live.py`** — trocar o conteúdo inteiro do arquivo (que hoje só tem `registrar`/`remover`/`publicar` da Task 2) pelo arquivo completo abaixo, com o endpoint acrescentado:

```python
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from .auth import verificar_token_query
from .meta import obter_sensor
from .odoo import get_cliente_servico

router = APIRouter()

_registry: dict[str, set[asyncio.Queue]] = {}


def registrar(sensor_code: str) -> asyncio.Queue:
    fila = asyncio.Queue()
    _registry.setdefault(sensor_code, set()).add(fila)
    return fila


def remover(sensor_code: str, fila: asyncio.Queue) -> None:
    filas = _registry.get(sensor_code)
    if filas is None:
        return
    filas.discard(fila)
    if not filas:
        _registry.pop(sensor_code, None)


def publicar(sensor_code: str, payload: dict) -> None:
    for fila in _registry.get(sensor_code, ()):
        fila.put_nowait(payload)


@router.get('/sensores/{sensor_code}/live')
async def get_live(
    sensor_code: str,
    cliente=Depends(get_cliente_servico),
    _claims=Depends(verificar_token_query),
):
    if obter_sensor(cliente, sensor_code) is None:
        raise HTTPException(status_code=404, detail=f"sensor '{sensor_code}' não encontrado")

    fila = registrar(sensor_code)

    async def stream():
        try:
            while True:
                payload = await fila.get()
                yield f"data: {json.dumps(payload)}\n\n"
        finally:
            remover(sensor_code, fila)

    return StreamingResponse(stream(), media_type='text/event-stream')
```

- [ ] **Step 5: Atualizar `api/main.py`** — trocar

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import auth, historico, meta

app = FastAPI(title='Sentinela API')

# Frontend (Vite dev) roda em origem diferente da API — sem isso o browser
# bloqueia a chamada por CORS. Portas fixas de dev (Vite tenta 5173 e sobe
# se ocupada); ajustar/restringir quando houver deploy real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[f'http://localhost:{p}' for p in range(5173, 5180)],
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(auth.router)
app.include_router(meta.router)
app.include_router(historico.router)


@app.get('/health')
def health():
    return {'status': 'ok'}
```

por

```python
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import auth, historico, live, live_listener, meta

app = FastAPI(title='Sentinela API')

# Frontend (Vite dev) roda em origem diferente da API — sem isso o browser
# bloqueia a chamada por CORS. Portas fixas de dev (Vite tenta 5173 e sobe
# se ocupada); ajustar/restringir quando houver deploy real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[f'http://localhost:{p}' for p in range(5173, 5180)],
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(auth.router)
app.include_router(meta.router)
app.include_router(historico.router)
app.include_router(live.router)


@app.on_event('startup')
async def _iniciar_live_listener():
    asyncio.create_task(live_listener.escutar())


@app.get('/health')
def health():
    return {'status': 'ok'}
```

- [ ] **Step 6: Rodar os testes e confirmar que passam**

Run: `python3 -m pytest api/tests/ -v`
Expected: 24 passed (17 já existentes + 1 `test_live_trigger.py` + 3 `test_live_registry.py` + 1 `test_live_listener.py` + 4 `test_live_endpoint.py`).

- [ ] **Step 7: Commit**

```bash
git add api/auth.py api/live.py api/main.py api/tests/test_live_endpoint.py
git commit -m "feat: endpoint SSE de feed ao vivo (auth por query token, 404 antes do stream)"
```

- [ ] **Step 8: Subir o servidor de verdade e verificar o fluxo ponta-a-ponta**

Run:
```bash
python3 -m uvicorn api.main:app --port 8001 &
UVPID=$!
sleep 2
TOKEN=$(curl -s -X POST http://localhost:8001/auth/login -H "Content-Type: application/json" -d '{"usuario":"admin","senha":"admin"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -N -s "http://localhost:8001/sensores/SNR-SIM-TEMP-01/live?token=$TOKEN" > /tmp/live_verificacao.txt &
CURLPID=$!
sleep 1

python3 -c "
import psycopg2
from datetime import datetime, timezone
conn = psycopg2.connect('postgresql://sentinela:sentinela@localhost:5433/sentinela')
agora = datetime.now(timezone.utc)
with conn.cursor() as cur:
    cur.execute(
        \"INSERT INTO sensor_reading (time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)\",
        (agora, 'SITE-SIM-0001', 'COL-SIM-0001', 'SNR-SIM-TEMP-01', 'AREA-SIM-EXPURGO', 'temperatura', 17.3, 'C', '4-20ma', 'ok'),
    )
conn.commit()
conn.close()
print('linha de verificacao inserida')
"

sleep 1
kill $CURLPID 2>/dev/null
kill $UVPID 2>/dev/null
cat /tmp/live_verificacao.txt
```
Expected: `/tmp/live_verificacao.txt` contém uma linha `data: {...}` com `"valor": 17.3` e `"sensor_id": "SNR-SIM-TEMP-01"`.

- [ ] **Step 9: Limpar a linha de verificação**

Run:
```bash
docker exec odoo_sentinela-timescaledb-1 psql -U sentinela -d sentinela -c "DELETE FROM sensor_reading WHERE sensor_id = 'SNR-SIM-TEMP-01' AND valor = 17.3;"
```
Expected: `DELETE 1`.

- [ ] **Step 10: Commit final de verificação**

```bash
git add -A
git commit -m "chore: verificacao final do feed ao vivo backend (trigger+listener+endpoint SSE)" --allow-empty
```
