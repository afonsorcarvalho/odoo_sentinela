# Fase 3 — API de Histórico Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `GET /sensores/{sensor_code}/historico?window=...` no serviço `api/`, servindo o shape `HistoryResponse` de `frontend/CONTRACTS.md` a partir do TimescaleDB (raw ou agregado, conforme a janela).

**Architecture:** `api/timescale.py` (consultas novas, reaproveita `ingestao.timescale.conectar`) + `api/historico.py` (endpoint, mapeamento janela→resolução→tabela, reaproveita `api/meta.py::obter_sensor` e `api/auth.py::verificar_token`).

**Tech Stack:** Mesmo da rodada anterior — FastAPI, `psycopg2` (via `ingestao.timescale`), TimescaleDB já rodando (`localhost:5433`).

## Global Constraints

- `sensor_reading.sensor_id` já é o `sensor_code` (string) — consulta direta, sem tradução via Odoo (só existência via `obter_sensor`, pra decidir `404`).
- Mapeamento de janela: `1h`→raw/`sensor_reading`; `24h`→agg/`sensor_reading_hourly`; `7d`→agg/`sensor_reading_hourly`; `30d`→agg/`sensor_reading_daily`.
- `ts` nos pontos de resposta em **milissegundos** (Unix × 1000).
- Nome de tabela agregada nunca vem de input do usuário — sempre de uma constante interna (`_JANELAS`), sem risco de injeção SQL por f-string.
- TimescaleDB e Odoo já rodam (`localhost:5433`/`http://localhost:8189`) — não subir/derrubar containers.
- **Limitação aceita nesta rodada**: `buscar_agregado`'s `WHERE bucket >= desde` compara contra o início do bucket (truncado pra hora/dia) — na borda de uma janela grande, o bucket mais antigo pode ter começado um pouco antes de `desde` e ficar de fora (perda de no máximo ~1 bucket na ponta, ex.: até 1h numa janela de 24h). Aceitável nesta fatia fina; refinar (`desde - largura_do_bucket`) fica para quando isso importar de verdade.

---

## Task 1: Consultas ao TimescaleDB (`api/timescale.py`)

**Files:**
- Create: `api/timescale.py`
- Test: `api/tests/test_timescale.py`

**Interfaces:**
- Consumes: `ingestao.timescale.conectar(dsn) -> connection`.
- Produces: `buscar_raw(conn, sensor_code, desde) -> list[dict]` (`{'time', 'valor'}`), `buscar_agregado(conn, sensor_code, tabela, desde) -> list[dict]` (`{'bucket', 'min', 'max', 'avg'}`) — usados pela Task 2.

- [ ] **Step 1: Escrever o teste em `api/tests/test_timescale.py`**

```python
from datetime import datetime, timedelta, timezone

from api import timescale as api_timescale
from ingestao.timescale import conectar

DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'
SENSOR_CODE_TESTE = 'SNR-HIST-TEST-01'


def _limpar():
    conn = conectar(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sensor_reading WHERE sensor_id = %s", (SENSOR_CODE_TESTE,))
        conn.commit()
    finally:
        conn.close()


def test_buscar_raw_retorna_leituras_recentes():
    conn = conectar(DSN)
    _limpar()
    try:
        agora = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sensor_reading "
                "(time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    agora - timedelta(minutes=10), 'SITE-TEST', 'COL-TEST', SENSOR_CODE_TESTE,
                    'AREA-TEST', 'temperatura', 21.5, 'C', '4-20ma', 'ok',
                ),
            )
        conn.commit()

        pontos = api_timescale.buscar_raw(conn, SENSOR_CODE_TESTE, agora - timedelta(hours=1))
        assert len(pontos) == 1
        assert pontos[0]['valor'] == 21.5
    finally:
        _limpar()
        conn.close()


def test_buscar_agregado_retorna_bucket_apos_refresh():
    conn = conectar(DSN)
    _limpar()
    try:
        agora = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sensor_reading "
                "(time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    agora - timedelta(minutes=10), 'SITE-TEST', 'COL-TEST', SENSOR_CODE_TESTE,
                    'AREA-TEST', 'temperatura', 21.5, 'C', '4-20ma', 'ok',
                ),
            )
        conn.commit()
        # refresh_continuous_aggregate() do Timescale so' roda fora de bloco de
        # transacao (levanta ActiveSqlTransaction dentro de uma) — autocommit
        # so' pra essa chamada, restaurado logo em seguida.
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "CALL refresh_continuous_aggregate('sensor_reading_hourly', %s, %s)",
                (agora - timedelta(hours=2), agora + timedelta(hours=1)),
            )
        conn.autocommit = False

        # desde com margem de 2h (nao 1h): o bucket horario trunca pro inicio
        # da hora, entao uma leitura de "10 min atras" pode cair num bucket
        # que comeca ANTES de "agora - 1h" se o teste rodar nos primeiros
        # minutos da hora corrente — 2h de margem garante que o teste nao
        # dependa do minuto do relogio em que roda (achado real, nao suposicao).
        pontos = api_timescale.buscar_agregado(
            conn, SENSOR_CODE_TESTE, 'sensor_reading_hourly', agora - timedelta(hours=2),
        )
        assert len(pontos) == 1
        assert pontos[0]['avg'] == 21.5
    finally:
        _limpar()
        conn.close()
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python3 -m pytest api/tests/test_timescale.py -v` (a partir da raiz do repo)
Expected: `ModuleNotFoundError: No module named 'api.timescale'`.

- [ ] **Step 3: Criar `api/timescale.py`**

```python
TABELAS_AGREGADO = {'sensor_reading_hourly', 'sensor_reading_daily'}


def buscar_raw(conn, sensor_code, desde):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT time, valor FROM sensor_reading WHERE sensor_id = %s AND time >= %s ORDER BY time",
            (sensor_code, desde),
        )
        linhas = cur.fetchall()
    return [{'time': linha[0], 'valor': linha[1]} for linha in linhas]


def buscar_agregado(conn, sensor_code, tabela, desde):
    if tabela not in TABELAS_AGREGADO:
        raise ValueError(f"tabela agregada desconhecida: {tabela}")
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT bucket, valor_min, valor_max, valor_avg FROM {tabela} "
            "WHERE sensor_id = %s AND bucket >= %s ORDER BY bucket",
            (sensor_code, desde),
        )
        linhas = cur.fetchall()
    return [{'bucket': linha[0], 'min': linha[1], 'max': linha[2], 'avg': linha[3]} for linha in linhas]
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `python3 -m pytest api/tests/test_timescale.py -v`
Expected: 2 passed. (O `conn.autocommit = True` ao redor do `CALL refresh_continuous_aggregate(...)` já está no código do Step 1 — necessário porque esse procedimento do Timescale não roda dentro de um bloco de transação; sem isso, levanta `psycopg2.errors.ActiveSqlTransaction`, confirmado empiricamente nesta sessão.)

- [ ] **Step 5: Commit**

```bash
git add api/timescale.py api/tests/test_timescale.py
git commit -m "feat: consultas ao TimescaleDB para historico (raw + agregado)"
```

---

## Task 2: Endpoint de histórico (`GET /sensores/{sensor_code}/historico`)

**Files:**
- Create: `api/historico.py`
- Modify: `api/main.py`
- Test: `api/tests/test_historico.py`

**Interfaces:**
- Consumes: `api.timescale.buscar_raw`, `api.timescale.buscar_agregado` (Task 1); `api.meta.obter_sensor`, `api.odoo.get_cliente_servico`, `api.auth.verificar_token` (rodada anterior); `ingestao.timescale.conectar`.
- Produces: `router` (montado em `api.main.app`).

- [ ] **Step 1: Escrever o teste em `api/tests/test_historico.py`**

```python
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from api.main import app
from ingestao.timescale import conectar

client = TestClient(app)
DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'
SENSOR_CODE = 'SNR-SIM-TEMP-01'


def _headers():
    resposta = client.post('/auth/login', json={'usuario': 'admin', 'senha': 'admin'})
    token = resposta.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def _limpar():
    conn = conectar(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sensor_reading WHERE sensor_id = %s", (SENSOR_CODE,))
        conn.commit()
    finally:
        conn.close()


def test_historico_1h_raw_retorna_pontos_inseridos():
    conn = conectar(DSN)
    _limpar()
    try:
        agora = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sensor_reading "
                "(time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    agora - timedelta(minutes=5), 'SITE-SIM-0001', 'COL-SIM-0001', SENSOR_CODE,
                    'AREA-SIM-EXPURGO', 'temperatura', 20.1, 'C', '4-20ma', 'ok',
                ),
            )
        conn.commit()

        resposta = client.get(f'/sensores/{SENSOR_CODE}/historico', params={'window': '1h'}, headers=_headers())
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo['sensor_code'] == SENSOR_CODE
        assert corpo['window'] == '1h'
        assert corpo['resolution'] == 'raw'
        assert len(corpo['points']) == 1
        assert corpo['points'][0]['value'] == 20.1
        assert 'ts' in corpo['points'][0]
    finally:
        _limpar()
        conn.close()


def test_historico_24h_agregado_apos_refresh():
    conn = conectar(DSN)
    _limpar()
    try:
        agora = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sensor_reading "
                "(time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    agora - timedelta(minutes=5), 'SITE-SIM-0001', 'COL-SIM-0001', SENSOR_CODE,
                    'AREA-SIM-EXPURGO', 'temperatura', 22.3, 'C', '4-20ma', 'ok',
                ),
            )
        conn.commit()
        # refresh_continuous_aggregate() do Timescale so' roda fora de bloco de
        # transacao — autocommit so' pra essa chamada, restaurado em seguida.
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "CALL refresh_continuous_aggregate('sensor_reading_hourly', %s, %s)",
                (agora - timedelta(hours=2), agora + timedelta(hours=1)),
            )
        conn.autocommit = False

        resposta = client.get(f'/sensores/{SENSOR_CODE}/historico', params={'window': '24h'}, headers=_headers())
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo['resolution'] == 'agg'
        assert len(corpo['points']) >= 1
        assert corpo['points'][0]['avg'] == 22.3
    finally:
        _limpar()
        conn.close()


def test_historico_sensor_inexistente_retorna_404():
    resposta = client.get('/sensores/SNR-NAO-EXISTE-XYZ/historico', params={'window': '1h'}, headers=_headers())
    assert resposta.status_code == 404


def test_historico_window_invalida_retorna_422():
    resposta = client.get(f'/sensores/{SENSOR_CODE}/historico', params={'window': '99x'}, headers=_headers())
    assert resposta.status_code == 422
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python3 -m pytest api/tests/test_historico.py -v`
Expected: `404` genérico do FastAPI (rota `/sensores/{code}/historico` ainda não existe).

- [ ] **Step 3: Criar `api/historico.py`**

```python
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from ingestao.timescale import conectar

from . import timescale as api_timescale
from .auth import verificar_token
from .meta import obter_sensor
from .odoo import get_cliente_servico

router = APIRouter()

DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'

_JANELAS = {
    '1h': {'resolution': 'raw', 'delta': timedelta(hours=1)},
    '24h': {'resolution': 'agg', 'tabela': 'sensor_reading_hourly', 'delta': timedelta(hours=24)},
    '7d': {'resolution': 'agg', 'tabela': 'sensor_reading_hourly', 'delta': timedelta(days=7)},
    '30d': {'resolution': 'agg', 'tabela': 'sensor_reading_daily', 'delta': timedelta(days=30)},
}


@router.get('/sensores/{sensor_code}/historico')
def get_historico(
    sensor_code: str,
    window: Literal['1h', '24h', '7d', '30d'],
    cliente=Depends(get_cliente_servico),
    _claims=Depends(verificar_token),
):
    if obter_sensor(cliente, sensor_code) is None:
        raise HTTPException(status_code=404, detail=f"sensor '{sensor_code}' não encontrado")

    config = _JANELAS[window]
    desde = datetime.now(timezone.utc) - config['delta']

    conn = conectar(DSN)
    try:
        if config['resolution'] == 'raw':
            linhas = api_timescale.buscar_raw(conn, sensor_code, desde)
            points = [{'ts': int(linha['time'].timestamp() * 1000), 'value': linha['valor']} for linha in linhas]
        else:
            linhas = api_timescale.buscar_agregado(conn, sensor_code, config['tabela'], desde)
            points = [
                {
                    'ts': int(linha['bucket'].timestamp() * 1000),
                    'min': linha['min'], 'max': linha['max'], 'avg': linha['avg'],
                }
                for linha in linhas
            ]
    finally:
        conn.close()

    return {
        'sensor_code': sensor_code,
        'window': window,
        'resolution': config['resolution'],
        'points': points,
    }
```

- [ ] **Step 4: Atualizar `api/main.py`** — trocar

```python
from fastapi import FastAPI

from . import auth, meta

app = FastAPI(title='Sentinela API')
app.include_router(auth.router)
app.include_router(meta.router)


@app.get('/health')
def health():
    return {'status': 'ok'}
```

por

```python
from fastapi import FastAPI

from . import auth, historico, meta

app = FastAPI(title='Sentinela API')
app.include_router(auth.router)
app.include_router(meta.router)
app.include_router(historico.router)


@app.get('/health')
def health():
    return {'status': 'ok'}
```

- [ ] **Step 5: Rodar os testes e confirmar que passam**

Run: `python3 -m pytest api/tests/ -v`
Expected: 16 passed (10 já existentes + 2 `test_timescale.py` + 4 `test_historico.py`).

- [ ] **Step 6: Commit**

```bash
git add api/historico.py api/main.py api/tests/test_historico.py
git commit -m "feat: endpoint de historico de sensor (raw/agregado por janela)"
```

---

## Task 3: Verificação final (suíte completa + servidor real + comparação com o contrato do frontend)

**Files:**
- Modify: nenhum arquivo novo — task de verificação/fechamento.

**Interfaces:**
- Consumes: tudo das Tasks 1–2, mais `api/auth.py`, `api/meta.py`, `api/odoo.py` da rodada anterior.

- [ ] **Step 1: Rodar a suíte completa**

Run (a partir da raiz do repo):
```bash
python3 -m pytest api/tests/ -v
```
Expected: 16 passed.

- [ ] **Step 2: Subir o servidor de verdade e testar com curl**

Run:
```bash
python3 -m uvicorn api.main:app --port 8001 &
sleep 2
TOKEN=$(curl -s -X POST http://localhost:8001/auth/login -H "Content-Type: application/json" -d '{"usuario":"admin","senha":"admin"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
python3 -c "
import psycopg2
from datetime import datetime, timedelta, timezone
conn = psycopg2.connect('postgresql://sentinela:sentinela@localhost:5433/sentinela')
agora = datetime.now(timezone.utc)
with conn.cursor() as cur:
    cur.execute(
        \"INSERT INTO sensor_reading (time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)\",
        (agora - timedelta(minutes=5), 'SITE-SIM-0001', 'COL-SIM-0001', 'SNR-SIM-TEMP-01', 'AREA-SIM-EXPURGO', 'temperatura', 19.7, 'C', '4-20ma', 'ok'),
    )
conn.commit()
conn.close()
print('linha de verificacao inserida')
"
curl -s "http://localhost:8001/sensores/SNR-SIM-TEMP-01/historico?window=1h" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
curl -s -o /dev/null -w "sem auth: %{http_code}\n" "http://localhost:8001/sensores/SNR-SIM-TEMP-01/historico?window=1h"
curl -s -o /dev/null -w "sensor inexistente: %{http_code}\n" "http://localhost:8001/sensores/SNR-XYZ/historico?window=1h" -H "Authorization: Bearer $TOKEN"
kill %1
```
Expected: JSON com `sensor_code`, `window: "1h"`, `resolution: "raw"`, um ponto com `value: 19.7`; `sem auth: 401`; `sensor inexistente: 404`.

- [ ] **Step 3: Conferir o shape contra `frontend/src/lib/types.ts`**

Run: `cat frontend/src/lib/types.ts`
Expected: `HistoryResponse`/`HistoryPoint` batem campo a campo com o JSON do Step 2.

- [ ] **Step 4: Limpar a linha de verificação inserida no Step 2**

Run:
```bash
docker compose exec timescaledb psql -U sentinela -d sentinela -c "DELETE FROM sensor_reading WHERE sensor_id = 'SNR-SIM-TEMP-01';"
```
Expected: `DELETE 1`.

- [ ] **Step 5: Commit final**

```bash
git add -A
git commit -m "chore: verificacao final da API de historico (Fase 3, segunda fatia)" --allow-empty
```
