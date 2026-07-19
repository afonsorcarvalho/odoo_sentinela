# Fase 3 — Auth/JWT + API de Meta Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Novo serviço FastAPI (`api/`) com login (Odoo → JWT) e três endpoints de metadados de sensor (`listar`, `obter`, `threshold`) servindo exatamente os shapes já congelados em `frontend/CONTRACTS.md`.

**Architecture:** `api/odoo.py` mantém uma conexão de serviço única com o Odoo (reaproveitando `ingestao.odoo_cliente`); `api/auth.py` valida credenciais e emite/verifica JWT; `api/meta.py` lê o cadastro Odoo e serializa nos shapes do contrato.

**Tech Stack:** FastAPI, `PyJWT`, `httpx` (TestClient), Odoo 18 já rodando (`http://localhost:8189`).

## Global Constraints

- Shapes de resposta devem bater **exatamente** com `frontend/CONTRACTS.md` (`SensorMeta`, `Threshold`) — nomes de campo, tipos, estrutura aninhada.
- `protocolo_origem` já é `4-20ma`/`rs485`/`i2c` (minúsculo) no Odoo — não reformatar.
- `Threshold.sensor_id` é o **`sensor_code`** (string), não o id numérico do Odoo — é assim que o frontend usa como chave.
- API usa uma conexão de serviço única (`admin`/`admin` via env vars) — sem filtragem multi-tenant nesta rodada.
- JWT: `PyJWT`, HS256, segredo via env var `API_JWT_SECRET` (default de dev), expiração 1h.
- Odoo já roda em `http://localhost:8189` (banco `sentinela`) — não subir/derrubar containers.

---

## Task 1: Esqueleto FastAPI + conexão de serviço com Odoo

**Files:**
- Create: `api/__init__.py`
- Create: `api/odoo.py`
- Create: `api/main.py`
- Create: `api/requirements.txt`
- Create: `api/tests/__init__.py`
- Test: `api/tests/test_main.py`

**Interfaces:**
- Produces: `get_cliente_servico() -> ClienteOdoo` (`api/odoo.py`, com `functools.lru_cache`) — usado pelas Tasks 2 e 3. App FastAPI exportado como `api.main.app`.

- [ ] **Step 1: Criar `api/requirements.txt`**

```
fastapi>=0.110
uvicorn[standard]>=0.29
pyjwt>=2.8
httpx>=0.27
pytest>=8
```

- [ ] **Step 2: Criar `api/__init__.py`** (vazio)

- [ ] **Step 3: Criar `api/tests/__init__.py`** (vazio)

- [ ] **Step 4: Escrever o teste em `api/tests/test_main.py`**

```python
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health():
    resposta = client.get('/health')
    assert resposta.status_code == 200
    assert resposta.json() == {'status': 'ok'}
```

- [ ] **Step 5: Rodar o teste e confirmar que falha**

Run: `python3 -m pytest api/tests/test_main.py -v` (a partir da raiz do repo)
Expected: `ModuleNotFoundError: No module named 'api.main'`.

- [ ] **Step 6: Criar `api/odoo.py`**

```python
import os
from functools import lru_cache

from ingestao import odoo_cliente

ODOO_URL = os.environ.get('ODOO_URL', 'http://localhost:8189')
ODOO_DB = os.environ.get('ODOO_DB', 'sentinela')
ODOO_USUARIO_SERVICO = os.environ.get('ODOO_USUARIO_SERVICO', 'admin')
ODOO_SENHA_SERVICO = os.environ.get('ODOO_SENHA_SERVICO', 'admin')


@lru_cache
def get_cliente_servico():
    return odoo_cliente.conectar(ODOO_URL, ODOO_DB, ODOO_USUARIO_SERVICO, ODOO_SENHA_SERVICO)
```

- [ ] **Step 7: Criar `api/main.py`**

```python
from fastapi import FastAPI

app = FastAPI(title='Sentinela API')


@app.get('/health')
def health():
    return {'status': 'ok'}
```

- [ ] **Step 8: Rodar o teste e confirmar que passa**

Run: `python3 -m pytest api/tests/test_main.py -v`
Expected: 1 passed.

- [ ] **Step 9: Commit**

```bash
git add api/__init__.py api/odoo.py api/main.py api/requirements.txt api/tests/__init__.py api/tests/test_main.py
git commit -m "feat: esqueleto FastAPI + conexao de servico com Odoo"
```

---

## Task 2: Autenticação (`POST /auth/login` + JWT)

**Files:**
- Create: `api/auth.py`
- Modify: `api/main.py`
- Test: `api/tests/test_auth.py`

**Interfaces:**
- Consumes: `ingestao.odoo_cliente.conectar`, `ingestao.odoo_cliente.executar`; `api.odoo.get_cliente_servico`, `ODOO_URL`, `ODOO_DB` (Task 1).
- Produces: `router` (FastAPI `APIRouter`, montado em `api.main.app`); `verificar_token` (dependency, usado pela Task 3); `SECRET`, `ALGORITHM` (usados nos testes para decodificar o token emitido).

- [ ] **Step 1: Escrever o teste em `api/tests/test_auth.py`**

```python
import jwt
from fastapi.testclient import TestClient

from api.auth import ALGORITHM, SECRET
from api.main import app

client = TestClient(app)


def test_login_com_credenciais_validas_retorna_token():
    resposta = client.post('/auth/login', json={'usuario': 'admin', 'senha': 'admin'})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo['token_type'] == 'bearer'
    payload = jwt.decode(corpo['access_token'], SECRET, algorithms=[ALGORITHM])
    assert 'sub' in payload
    assert 'partner_id' in payload
    assert 'exp' in payload


def test_login_com_senha_errada_retorna_401():
    resposta = client.post('/auth/login', json={'usuario': 'admin', 'senha': 'senha_errada_xyz'})
    assert resposta.status_code == 401
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python3 -m pytest api/tests/test_auth.py -v`
Expected: `ModuleNotFoundError: No module named 'api.auth'`.

- [ ] **Step 3: Criar `api/auth.py`**

```python
import os
import time

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from ingestao import odoo_cliente

from .odoo import ODOO_DB, ODOO_URL, get_cliente_servico

SECRET = os.environ.get('API_JWT_SECRET', 'dev-secret-troque-em-producao')
ALGORITHM = 'HS256'
EXPIRACAO_SEGUNDOS = 3600

router = APIRouter()
_security = HTTPBearer()


class LoginRequest(BaseModel):
    usuario: str
    senha: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'


@router.post('/auth/login', response_model=LoginResponse)
def login(dados: LoginRequest):
    try:
        cliente_usuario = odoo_cliente.conectar(ODOO_URL, ODOO_DB, dados.usuario, dados.senha)
    except RuntimeError:
        raise HTTPException(status_code=401, detail='credenciais inválidas')

    cliente_servico = get_cliente_servico()
    usuarios = odoo_cliente.executar(
        cliente_servico, 'res.users', 'read', [cliente_usuario.uid], fields=['partner_id'],
    )
    partner_id = usuarios[0]['partner_id'][0]

    payload = {
        'sub': cliente_usuario.uid,
        'partner_id': partner_id,
        'exp': int(time.time()) + EXPIRACAO_SEGUNDOS,
    }
    token = jwt.encode(payload, SECRET, algorithm=ALGORITHM)
    return LoginResponse(access_token=token)


def verificar_token(credenciais: HTTPAuthorizationCredentials = Depends(_security)):
    try:
        return jwt.decode(credenciais.credentials, SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail='token inválido ou expirado')
```

- [ ] **Step 4: Atualizar `api/main.py`** — trocar

```python
from fastapi import FastAPI

app = FastAPI(title='Sentinela API')


@app.get('/health')
def health():
    return {'status': 'ok'}
```

por

```python
from fastapi import FastAPI

from . import auth

app = FastAPI(title='Sentinela API')
app.include_router(auth.router)


@app.get('/health')
def health():
    return {'status': 'ok'}
```

- [ ] **Step 5: Rodar os testes e confirmar que passam**

Run: `python3 -m pytest api/tests/ -v`
Expected: 3 passed (1 de `test_main.py` + 2 de `test_auth.py`).

- [ ] **Step 6: Commit**

```bash
git add api/auth.py api/main.py
git commit -m "feat: endpoint de login com Odoo + emissao/verificacao de JWT"
```

---

## Task 3: Metadados de sensor (`GET /sensores`, `/sensores/{code}`, `/sensores/{code}/threshold`)

**Files:**
- Create: `api/meta.py`
- Modify: `api/main.py`
- Test: `api/tests/test_meta.py`

**Interfaces:**
- Consumes: `api.auth.verificar_token`, `api.odoo.get_cliente_servico` (Tasks 1, 2); `ingestao.odoo_cliente.executar`.
- Produces: `router` (montado em `api.main.app`); `listar_sensores`, `obter_sensor`, `obter_threshold` (funções puras, testáveis independente do HTTP).

- [ ] **Step 1: Escrever o teste em `api/tests/test_meta.py`**

```python
from fastapi.testclient import TestClient

from api.main import app
from api.odoo import get_cliente_servico
from ingestao import odoo_cliente

client = TestClient(app)


def _headers():
    resposta = client.post('/auth/login', json={'usuario': 'admin', 'senha': 'admin'})
    token = resposta.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def test_listar_sensores_sem_token_retorna_401():
    resposta = client.get('/sensores')
    assert resposta.status_code == 401


def test_listar_sensores_com_token_retorna_lista():
    resposta = client.get('/sensores', headers=_headers())
    assert resposta.status_code == 200
    codigos = [s['sensor_code'] for s in resposta.json()]
    assert 'TEMP-01' in codigos
    assert 'SNR-SIM-TEMP-01' in codigos


def test_obter_sensor_existente_bate_shape():
    resposta = client.get('/sensores/SNR-SIM-TEMP-01', headers=_headers())
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo['sensor_code'] == 'SNR-SIM-TEMP-01'
    assert corpo['protocolo_origem'] == '4-20ma'
    assert corpo['measurement_type']['code'] == 'temperatura'
    assert corpo['area']['category'] == 'Expurgo'


def test_obter_sensor_inexistente_retorna_404():
    resposta = client.get('/sensores/SNR-NAO-EXISTE-XYZ', headers=_headers())
    assert resposta.status_code == 404


def test_threshold_sensor_sem_limiar_retorna_null():
    resposta = client.get('/sensores/SNR-SIM-TEMP-01/threshold', headers=_headers())
    assert resposta.status_code == 200
    assert resposta.json() is None


def test_threshold_sensor_com_limiar_retorna_valores():
    cliente = get_cliente_servico()
    sensor_ids = odoo_cliente.executar(
        cliente, 'sensor_monitor.sensor', 'search', [('sensor_code', '=', 'SNR-SIM-PRES-01')],
    )
    threshold_id = odoo_cliente.executar(
        cliente, 'sensor_monitor.alarm.threshold', 'create',
        {'sensor_id': sensor_ids[0], 'limite_min': -10.0, 'limite_max': -2.5, 'is_valor_padrao_regulatorio': True},
    )
    try:
        resposta = client.get('/sensores/SNR-SIM-PRES-01/threshold', headers=_headers())
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo['sensor_id'] == 'SNR-SIM-PRES-01'
        assert corpo['limite_min'] == -10.0
        assert corpo['limite_max'] == -2.5
        assert corpo['is_valor_padrao_regulatorio'] is True
    finally:
        odoo_cliente.executar(cliente, 'sensor_monitor.alarm.threshold', 'unlink', [threshold_id])


def test_threshold_sensor_inexistente_retorna_404():
    resposta = client.get('/sensores/SNR-NAO-EXISTE-XYZ/threshold', headers=_headers())
    assert resposta.status_code == 404
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python3 -m pytest api/tests/test_meta.py -v`
Expected: `404` genérico do FastAPI pra rotas inexistentes em vez dos comportamentos esperados (rotas `/sensores*` ainda não existem).

- [ ] **Step 3: Criar `api/meta.py`**

```python
from fastapi import APIRouter, Depends, HTTPException

from ingestao import odoo_cliente

from .auth import verificar_token
from .odoo import get_cliente_servico

router = APIRouter()

_CAMPOS_SENSOR = ['sensor_code', 'name', 'unidade', 'protocolo_origem', 'area_id', 'measurement_type_id']


def _serializar_sensor(cliente, sensor):
    area = odoo_cliente.executar(
        cliente, 'sensor_monitor.area', 'read', [sensor['area_id'][0]],
        fields=['area_code', 'name', 'area_category_id'],
    )[0]
    categoria = odoo_cliente.executar(
        cliente, 'sensor_monitor.area.category', 'read', [area['area_category_id'][0]], fields=['name'],
    )[0]
    tipo_medida = odoo_cliente.executar(
        cliente, 'sensor_monitor.measurement.type', 'read', [sensor['measurement_type_id'][0]],
        fields=['code', 'name', 'unidade_padrao'],
    )[0]
    return {
        'sensor_code': sensor['sensor_code'],
        'name': sensor['name'],
        'unidade': sensor['unidade'] or tipo_medida['unidade_padrao'],
        'protocolo_origem': sensor['protocolo_origem'],
        'measurement_type': {'code': tipo_medida['code'], 'name': tipo_medida['name']},
        'area': {'area_code': area['area_code'], 'name': area['name'], 'category': categoria['name']},
    }


def listar_sensores(cliente):
    sensores = odoo_cliente.executar(cliente, 'sensor_monitor.sensor', 'search_read', [], fields=_CAMPOS_SENSOR)
    return [_serializar_sensor(cliente, s) for s in sensores]


def obter_sensor(cliente, sensor_code):
    sensores = odoo_cliente.executar(
        cliente, 'sensor_monitor.sensor', 'search_read',
        [('sensor_code', '=', sensor_code)], fields=_CAMPOS_SENSOR,
    )
    if not sensores:
        return None
    return _serializar_sensor(cliente, sensores[0])


def obter_threshold(cliente, sensor_code):
    sensor_ids = odoo_cliente.executar(
        cliente, 'sensor_monitor.sensor', 'search', [('sensor_code', '=', sensor_code)],
    )
    if not sensor_ids:
        raise ValueError(f"sensor '{sensor_code}' não encontrado")
    thresholds = odoo_cliente.executar(
        cliente, 'sensor_monitor.alarm.threshold', 'search_read',
        [('sensor_id', '=', sensor_ids[0])],
        fields=['limite_min', 'limite_max', 'is_valor_padrao_regulatorio'],
    )
    if not thresholds:
        return None
    t = thresholds[0]
    return {
        'sensor_id': sensor_code,
        'limite_min': t['limite_min'],
        'limite_max': t['limite_max'],
        'is_valor_padrao_regulatorio': t['is_valor_padrao_regulatorio'],
    }


@router.get('/sensores')
def get_sensores(cliente=Depends(get_cliente_servico), _claims=Depends(verificar_token)):
    return listar_sensores(cliente)


@router.get('/sensores/{sensor_code}')
def get_sensor(sensor_code: str, cliente=Depends(get_cliente_servico), _claims=Depends(verificar_token)):
    resultado = obter_sensor(cliente, sensor_code)
    if resultado is None:
        raise HTTPException(status_code=404, detail=f"sensor '{sensor_code}' não encontrado")
    return resultado


@router.get('/sensores/{sensor_code}/threshold')
def get_threshold(sensor_code: str, cliente=Depends(get_cliente_servico), _claims=Depends(verificar_token)):
    try:
        return obter_threshold(cliente, sensor_code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
```

- [ ] **Step 4: Atualizar `api/main.py`** — trocar

```python
from fastapi import FastAPI

from . import auth

app = FastAPI(title='Sentinela API')
app.include_router(auth.router)


@app.get('/health')
def health():
    return {'status': 'ok'}
```

por

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

- [ ] **Step 5: Rodar os testes e confirmar que passam**

Run: `python3 -m pytest api/tests/ -v`
Expected: 10 passed (1 `test_main` + 2 `test_auth` + 7 `test_meta`).

- [ ] **Step 6: Commit**

```bash
git add api/meta.py api/main.py
git commit -m "feat: endpoints de metadados de sensor (listar, obter, threshold)"
```

---

## Task 4: Verificação final (suíte completa + servidor real + comparação com o contrato do frontend)

**Files:**
- Modify: nenhum arquivo novo — task de verificação/fechamento.

**Interfaces:**
- Consumes: tudo das Tasks 1–3.

- [ ] **Step 1: Instalar dependências e rodar a suíte completa**

Run (a partir da raiz do repo):
```bash
pip install -r api/requirements.txt
python3 -m pytest api/tests/ -v
```
Expected: 10 passed.

- [ ] **Step 2: Subir o servidor de verdade e testar com curl**

Run:
```bash
python3 -m uvicorn api.main:app --port 8001 &
sleep 2
TOKEN=$(curl -s -X POST http://localhost:8001/auth/login -H "Content-Type: application/json" -d '{"usuario":"admin","senha":"admin"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
curl -s http://localhost:8001/sensores -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
curl -s http://localhost:8001/sensores/SNR-SIM-TEMP-01 -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
curl -s http://localhost:8001/sensores/SNR-SIM-TEMP-01/threshold -H "Authorization: Bearer $TOKEN"
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8001/sensores
kill %1
```
Expected: lista de sensores com `TEMP-01`/`SNR-SIM-TEMP-01`/`SNR-SIM-PRES-01`; objeto `SensorMeta` completo pro segundo comando; `null` pro terceiro (sem threshold); `401` pro quarto (sem header de auth).

- [ ] **Step 3: Conferir o shape contra `frontend/CONTRACTS.md` e `frontend/src/lib/types.ts` manualmente**

Run: `cat frontend/src/lib/types.ts` (ou o arquivo que define `SensorMeta`/`Threshold` em TypeScript) e comparar campo a campo com o JSON do Step 2.
Expected: nomes de campo e estrutura aninhada idênticos — nenhuma divergência.

- [ ] **Step 4: Commit final**

```bash
git add -A
git commit -m "chore: verificacao final da API de auth+meta (Fase 3, primeira fatia)" --allow-empty
```
