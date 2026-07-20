# Isolamento Multi-Tenant na API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar o vazamento cross-tenant na API (`api/`): nenhuma consulta a dado de sensor/site/hub/coletor/alarme, nem leitura/histórico/SSE do TimescaleDB, deve retornar dado de um cliente para o usuário autenticado de outro cliente.

**Architecture:** No login, a API guarda a sessão Odoo real do usuário (cache server-side, chave = `jti` do JWT) em vez de descartá-la. Endpoints que leem modelos Odoo passam a rodar como esse usuário real — o `ir.rule` já existente no addon (`security_rules.xml`) filtra sozinho. Para o TimescaleDB (que não tem `ir.rule`), a lista de sites permitidos vem do Odoo (via a mesma sessão) e vira parâmetro obrigatório nas funções de consulta e no registro de conexões SSE.

**Tech Stack:** FastAPI, PyJWT, XML-RPC (`ingestao.odoo_cliente`, já existente), psycopg2 (`ingestao.timescale`, já existente), pytest contra Odoo 18 e TimescaleDB reais já rodando.

## Global Constraints

- Nenhum endpoint que responde a um usuário autenticado usa `get_cliente_servico` para buscar o dado — só para lookups internos do próprio login (`partner_id`/`is_admin`) e para fixtures/setup de teste.
- `sites_permitidos` é sempre `list[str]` de `site_code` (não IDs numéricos do Odoo) — mesmo formato já usado na coluna `site_id` da tabela `sensor_reading` do Timescale.
- Toda função de leitura no Timescale que precisa respeitar tenant recebe `sites_permitidos` como parâmetro **obrigatório** (sem default) — nunca uma checagem opcional.
- `API_JWT_SECRET` obrigatório — o processo da API recusa subir sem essa variável de ambiente definida.
- Testes rodam contra Odoo real (`http://localhost:8189`, banco `sentinela`) e TimescaleDB real (`postgresql://sentinela:sentinela@localhost:5433/sentinela`), ambos já em execução — não subir/derrubar containers durante o plano.
- Login `admin`/`admin` já pertence ao grupo `afr_sentinela_sensor_monitor.group_sensor_monitor_admin` (confirmado empiricamente) e por isso enxerga todos os sites via `ir.rule` — os testes existentes que logam como admin continuam passando sem alteração de expectativa.
- Fixture de tenant de teste usa os grupos `afr_sentinela_sensor_monitor.group_sensor_monitor_view` + `base.group_user` (mínimo pra um usuário logar e ler os próprios dados).
- `config.py`/`dashboard_config` está **fora de escopo** deste plano (rastreado em `TODO.md` como bloqueante de produção, separado).

---

## Task 1: Sessão do usuário — cache server-side, `API_JWT_SECRET` obrigatório, `get_cliente_usuario`

**Files:**
- Create: `api/sessions.py`
- Create: `api/tests/test_sessions.py`
- Create: `api/tests/conftest.py`
- Modify: `api/auth.py`
- Modify: `api/tests/test_auth.py`

**Interfaces:**
- Consumes: `ingestao.odoo_cliente.conectar`, `ingestao.odoo_cliente.executar`, `api.odoo.get_cliente_servico`, `ODOO_URL`, `ODOO_DB` (já existentes).
- Produces: `api.sessions.guardar(jti: str, cliente, exp: int)`, `api.sessions.obter(jti: str) -> ClienteOdoo | None`, `api.sessions.remover(jti: str)` — usados pela Task 2, 3, 4. `api.auth.get_cliente_usuario(claims: dict = Depends(verificar_token)) -> ClienteOdoo` e `api.auth.get_cliente_usuario_query(claims: dict = Depends(verificar_token_query)) -> ClienteOdoo` — dependencies FastAPI usadas pelas Tasks 2, 3, 4 no lugar de `get_cliente_servico`.

- [ ] **Step 1: Escrever o teste em `api/tests/test_sessions.py`**

```python
import time

from api import sessions


def test_guardar_e_obter_retorna_cliente():
    sessions.guardar('jti-1', 'cliente-fake', exp=int(time.time()) + 60)
    assert sessions.obter('jti-1') == 'cliente-fake'
    sessions.remover('jti-1')


def test_obter_jti_inexistente_retorna_none():
    assert sessions.obter('jti-nao-existe') is None


def test_obter_sessao_expirada_retorna_none_e_remove():
    sessions.guardar('jti-expirado', 'cliente-fake', exp=int(time.time()) - 1)
    assert sessions.obter('jti-expirado') is None
    assert sessions.obter('jti-expirado') is None


def test_remover_apaga_sessao():
    sessions.guardar('jti-2', 'cliente-fake', exp=int(time.time()) + 60)
    sessions.remover('jti-2')
    assert sessions.obter('jti-2') is None
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `python3 -m pytest api/tests/test_sessions.py -v` (a partir da raiz do repo)
Expected: `ModuleNotFoundError: No module named 'api.sessions'`.

- [ ] **Step 3: Criar `api/sessions.py`**

```python
import threading
import time

_lock = threading.Lock()
_sessions = {}


def guardar(jti, cliente, exp):
    with _lock:
        _sessions[jti] = (cliente, exp)


def obter(jti):
    with _lock:
        entrada = _sessions.get(jti)
        if entrada is None:
            return None
        cliente, exp = entrada
        if exp < time.time():
            del _sessions[jti]
            return None
        return cliente


def remover(jti):
    with _lock:
        _sessions.pop(jti, None)
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

Run: `python3 -m pytest api/tests/test_sessions.py -v`
Expected: 4 passed.

- [ ] **Step 5: Criar `api/tests/conftest.py`**

```python
import os

os.environ.setdefault('API_JWT_SECRET', 'segredo-de-teste-pytest-nao-usar-em-producao')
```

- [ ] **Step 6: Escrever o teste de fail-fast em `api/tests/test_auth.py`** — adicionar ao arquivo existente:

```python
def test_auth_falha_ao_subir_sem_api_jwt_secret():
    raiz_repo = subprocess.run(
        ['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True,
    ).stdout.strip()
    env = {k: v for k, v in os.environ.items() if k != 'API_JWT_SECRET'}
    resultado = subprocess.run(
        ['python3', '-c', 'import api.auth'],
        cwd=raiz_repo, env=env, capture_output=True, text=True,
    )
    assert resultado.returncode != 0
    assert 'API_JWT_SECRET' in resultado.stderr
```

E no topo do arquivo, junto aos imports existentes (`import jwt`, `from fastapi.testclient import TestClient`), adicionar:

```python
import os
import subprocess

import pytest
```

- [ ] **Step 7: Rodar o teste e confirmar que falha**

Run: `python3 -m pytest api/tests/test_auth.py::test_auth_falha_ao_subir_sem_api_jwt_secret -v`
Expected: FAIL — `assert 0 != 0` (hoje `import api.auth` funciona sem a variável, por causa do default `dev-secret-troque-em-producao`).

- [ ] **Step 8: Modificar `api/auth.py`** — substituir todo o conteúdo do arquivo por:

```python
import os
import time
import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from ingestao import odoo_cliente

from . import sessions
from .odoo import ODOO_DB, ODOO_URL, get_cliente_servico

SECRET = os.environ.get('API_JWT_SECRET')
if not SECRET:
    raise RuntimeError(
        "API_JWT_SECRET não definido. Defina a variável de ambiente antes de subir a API "
        "(sem isso, tokens JWT usariam um segredo previsível e poderiam ser forjados)."
    )
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

    # `has_group` via XML-RPC execute_kw não aceita a assinatura direta
    # (falha em runtime: "missing 1 required positional argument: 'group_ext_id'").
    # Alternativa equivalente: resolver o xml_id técnico base.group_system
    # (imune a locale, ao contrário de buscar por full_name traduzível) e
    # checar se o uid logado pertence ao grupo correspondente.
    dados_modelo = odoo_cliente.executar(
        cliente_servico, 'ir.model.data', 'search_read',
        [('module', '=', 'base'), ('name', '=', 'group_system')], fields=['res_id'], limit=1,
    )
    is_admin = False
    if dados_modelo:
        usuarios_admin = odoo_cliente.executar(
            cliente_servico, 'res.users', 'search_read',
            [('id', '=', cliente_usuario.uid), ('groups_id', 'in', dados_modelo[0]['res_id'])], fields=['id'],
        )
        is_admin = bool(usuarios_admin)

    jti = uuid.uuid4().hex
    exp = int(time.time()) + EXPIRACAO_SEGUNDOS
    sessions.guardar(jti, cliente_usuario, exp)

    payload = {
        'sub': str(cliente_usuario.uid),
        'partner_id': partner_id,
        'is_admin': is_admin,
        'jti': jti,
        'exp': exp,
    }
    token = jwt.encode(payload, SECRET, algorithm=ALGORITHM)
    return LoginResponse(access_token=token)


def verificar_token(credenciais: HTTPAuthorizationCredentials = Depends(_security)):
    try:
        return jwt.decode(credenciais.credentials, SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail='token inválido ou expirado')


def verificar_token_query(token: str):
    try:
        return jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail='token inválido ou expirado')


def exigir_admin(claims: dict = Depends(verificar_token)):
    if not claims.get('is_admin'):
        raise HTTPException(status_code=403, detail='requer privilégio de administrador')
    return claims


def resolver_cliente_usuario(claims: dict):
    cliente = sessions.obter(claims['jti'])
    if cliente is None:
        raise HTTPException(status_code=401, detail='sessão expirada — faça login novamente')
    return cliente


def get_cliente_usuario(claims: dict = Depends(verificar_token)):
    return resolver_cliente_usuario(claims)


def get_cliente_usuario_query(claims: dict = Depends(verificar_token_query)):
    return resolver_cliente_usuario(claims)
```

- [ ] **Step 9: Rodar o teste do Step 6/7 e confirmar que passa**

Run: `python3 -m pytest api/tests/test_auth.py::test_auth_falha_ao_subir_sem_api_jwt_secret -v`
Expected: 1 passed.

- [ ] **Step 10: Escrever os testes de `jti`/`get_cliente_usuario` em `api/tests/test_auth.py`** — adicionar:

```python
def test_login_inclui_jti_e_permite_obter_cliente_usuario():
    from api.auth import get_cliente_usuario

    resposta = client.post('/auth/login', json={'usuario': 'admin', 'senha': 'admin'})
    corpo = resposta.json()
    payload = jwt.decode(corpo['access_token'], SECRET, algorithms=[ALGORITHM])
    assert 'jti' in payload

    cliente = get_cliente_usuario(payload)
    assert str(cliente.uid) == payload['sub']


def test_get_cliente_usuario_sem_sessao_valida_levanta_401():
    from fastapi import HTTPException

    from api.auth import get_cliente_usuario

    with pytest.raises(HTTPException) as exc:
        get_cliente_usuario({'jti': 'jti-que-nao-existe'})
    assert exc.value.status_code == 401
```

- [ ] **Step 11: Rodar toda a suíte de `test_sessions.py` e `test_auth.py` e confirmar que passa**

Run: `python3 -m pytest api/tests/test_sessions.py api/tests/test_auth.py -v`
Expected: 9 passed (4 de `test_sessions.py` + 5 de `test_auth.py`).

- [ ] **Step 12: Commit**

```bash
git add api/sessions.py api/auth.py api/tests/test_sessions.py api/tests/test_auth.py api/tests/conftest.py
git commit -m "feat: sessao real do usuario no Odoo (jti + cache server-side) e API_JWT_SECRET obrigatorio"
```

---

## Task 2: Fixture de tenant de teste + `meta.py`/`alarmes.py` usam a sessão real do usuário

**Files:**
- Create: `api/tests/tenant_fixtures.py`
- Modify: `api/meta.py`
- Modify: `api/alarmes.py`
- Modify: `api/tests/test_meta.py`
- Modify: `api/tests/test_alarmes.py`

**Interfaces:**
- Consumes: `api.auth.get_cliente_usuario` (Task 1); `api.odoo.get_cliente_servico`; `ingestao.odoo_cliente.executar`.
- Produces: `api.tests.tenant_fixtures.criar_tenant(sufixo: str) -> dict` (chaves: `partner_id`, `site_id`, `site_code`, `hub_id`, `coletor_id`, `area_id`, `sensor_id`, `sensor_code`, `user_id`, `login`, `senha`) e `api.tests.tenant_fixtures.remover_tenant(dados: dict)` — usados pelas Tasks 3 e 4.

- [ ] **Step 1: Criar `api/tests/tenant_fixtures.py`**

```python
from api.odoo import get_cliente_servico
from ingestao import odoo_cliente

_SENHA_PADRAO = 'senha-teste-tenant-123'


def criar_tenant(sufixo):
    cliente = get_cliente_servico()

    partner_id = odoo_cliente.executar(
        cliente, 'res.partner', 'create', {'name': f'Cliente Teste {sufixo}'},
    )
    site_code = f'SITE-TENANT-{sufixo}'
    site_id = odoo_cliente.executar(
        cliente, 'sensor_monitor.site', 'create', {
            'name': f'Site Teste {sufixo}', 'partner_id': partner_id,
            'site_code': site_code, 'vertical': 'cme_hospitalar',
        },
    )
    hub_id = odoo_cliente.executar(
        cliente, 'sensor_monitor.hub', 'create', {
            'name': f'Hub Teste {sufixo}', 'site_id': site_id, 'hub_code': f'HUB-TENANT-{sufixo}',
        },
    )
    coletor_id = odoo_cliente.executar(
        cliente, 'sensor_monitor.coletor', 'create', {
            'name': f'Coletor Teste {sufixo}', 'hub_id': hub_id,
            'coletor_code': f'COL-TENANT-{sufixo}', 'tipo': 'esp32_wifi',
        },
    )
    categoria_id = odoo_cliente.executar(cliente, 'sensor_monitor.area.category', 'search', [], limit=1)[0]
    area_id = odoo_cliente.executar(
        cliente, 'sensor_monitor.area', 'create', {
            'name': f'Área Teste {sufixo}', 'site_id': site_id,
            'area_category_id': categoria_id, 'area_code': f'AREA-TENANT-{sufixo}',
        },
    )
    tipo_medida_id = odoo_cliente.executar(cliente, 'sensor_monitor.measurement.type', 'search', [], limit=1)[0]
    sensor_code = f'SNR-TENANT-{sufixo}'
    sensor_id = odoo_cliente.executar(
        cliente, 'sensor_monitor.sensor', 'create', {
            'name': f'Sensor Teste {sufixo}', 'sensor_code': sensor_code,
            'coletor_id': coletor_id, 'area_id': area_id, 'measurement_type_id': tipo_medida_id,
            'protocolo_origem': '4-20ma',
        },
    )
    view_group_id = odoo_cliente.executar(
        cliente, 'ir.model.data', 'search_read',
        [('module', '=', 'afr_sentinela_sensor_monitor'), ('name', '=', 'group_sensor_monitor_view')],
        fields=['res_id'], limit=1,
    )[0]['res_id']
    base_user_group_id = odoo_cliente.executar(
        cliente, 'ir.model.data', 'search_read',
        [('module', '=', 'base'), ('name', '=', 'group_user')], fields=['res_id'], limit=1,
    )[0]['res_id']
    login = f'usuario.tenant.{sufixo}@teste.com'.lower()
    user_id = odoo_cliente.executar(
        cliente, 'res.users', 'create', {
            'name': f'Usuário Tenant {sufixo}', 'login': login, 'password': _SENHA_PADRAO,
            'partner_id': partner_id, 'groups_id': [(6, 0, [view_group_id, base_user_group_id])],
        },
    )
    return {
        'partner_id': partner_id, 'site_id': site_id, 'site_code': site_code,
        'hub_id': hub_id, 'coletor_id': coletor_id, 'area_id': area_id,
        'sensor_id': sensor_id, 'sensor_code': sensor_code,
        'user_id': user_id, 'login': login, 'senha': _SENHA_PADRAO,
    }


def remover_tenant(dados):
    cliente = get_cliente_servico()
    odoo_cliente.executar(cliente, 'res.users', 'unlink', [dados['user_id']])
    odoo_cliente.executar(cliente, 'sensor_monitor.sensor', 'unlink', [dados['sensor_id']])
    odoo_cliente.executar(cliente, 'sensor_monitor.area', 'unlink', [dados['area_id']])
    odoo_cliente.executar(cliente, 'sensor_monitor.coletor', 'unlink', [dados['coletor_id']])
    odoo_cliente.executar(cliente, 'sensor_monitor.hub', 'unlink', [dados['hub_id']])
    odoo_cliente.executar(cliente, 'sensor_monitor.site', 'unlink', [dados['site_id']])
    odoo_cliente.executar(cliente, 'res.partner', 'unlink', [dados['partner_id']])
```

Esta fixture já foi validada manualmente contra o Odoo real rodando (`http://localhost:8189`, banco `sentinela`): cria partner/site/hub/coletor/área/sensor/usuário, o usuário criado loga e vê exatamente o próprio site/sensor via `ir.rule`, e a limpeza funciona sem erro de FK.

- [ ] **Step 2: Escrever os testes de isolamento em `api/tests/test_meta.py`** — adicionar ao arquivo existente:

```python
from api.tests.tenant_fixtures import criar_tenant, remover_tenant


def _headers_para(login, senha):
    resposta = client.post('/auth/login', json={'usuario': login, 'senha': senha})
    token = resposta.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def test_obter_sensor_de_outro_tenant_retorna_404():
    tenant_a = criar_tenant('META-A')
    tenant_b = criar_tenant('META-B')
    try:
        resposta = client.get(
            f"/sensores/{tenant_b['sensor_code']}",
            headers=_headers_para(tenant_a['login'], tenant_a['senha']),
        )
        assert resposta.status_code == 404
    finally:
        remover_tenant(tenant_a)
        remover_tenant(tenant_b)


def test_listar_sensores_nao_inclui_sensor_de_outro_tenant():
    tenant_a = criar_tenant('META-LIST-A')
    tenant_b = criar_tenant('META-LIST-B')
    try:
        resposta = client.get('/sensores', headers=_headers_para(tenant_a['login'], tenant_a['senha']))
        codigos = [s['sensor_code'] for s in resposta.json()]
        assert tenant_a['sensor_code'] in codigos
        assert tenant_b['sensor_code'] not in codigos
    finally:
        remover_tenant(tenant_a)
        remover_tenant(tenant_b)
```

- [ ] **Step 3: Rodar os testes novos e confirmar que falham**

Run: `python3 -m pytest api/tests/test_meta.py -k outro_tenant -v`
Expected: FAIL — hoje `/sensores` e `/sensores/{code}` usam `get_cliente_servico` (vê tudo), então o sensor do tenant B aparece pro tenant A.

- [ ] **Step 4: Modificar `api/meta.py`** — trocar

```python
from fastapi import APIRouter, Depends, HTTPException

from ingestao import odoo_cliente

from .auth import verificar_token
from .odoo import get_cliente_servico
```

por

```python
from fastapi import APIRouter, Depends, HTTPException

from ingestao import odoo_cliente

from .auth import get_cliente_usuario, verificar_token
```

E trocar as três ocorrências de `cliente=Depends(get_cliente_servico)` por `cliente=Depends(get_cliente_usuario)` nas rotas `get_sensores`, `get_sensor`, `get_threshold`.

- [ ] **Step 5: Escrever o teste de isolamento em `api/tests/test_alarmes.py`** — adicionar:

```python
from api.tests.tenant_fixtures import criar_tenant, remover_tenant


def test_listar_alarmes_nao_inclui_evento_de_outro_tenant():
    cliente_servico = get_cliente_servico()
    tenant_a = criar_tenant('ALARM-A')
    tenant_b = criar_tenant('ALARM-B')
    evento_b_id = _criar_evento(cliente_servico, tenant_b['sensor_code'])
    try:
        resposta_login = client.post('/auth/login', json={'usuario': tenant_a['login'], 'senha': tenant_a['senha']})
        token = resposta_login.json()['access_token']
        resposta = client.get('/alarmes', headers={'Authorization': f'Bearer {token}'})
        ids = {e['id'] for e in resposta.json()}
        assert evento_b_id not in ids
    finally:
        _apagar(cliente_servico, evento_b_id)
        remover_tenant(tenant_a)
        remover_tenant(tenant_b)
```

- [ ] **Step 6: Rodar o teste novo e confirmar que falha**

Run: `python3 -m pytest api/tests/test_alarmes.py::test_listar_alarmes_nao_inclui_evento_de_outro_tenant -v`
Expected: FAIL — `/alarmes` hoje usa `get_cliente_servico`, então o evento do tenant B aparece pro tenant A.

- [ ] **Step 7: Modificar `api/alarmes.py`** — trocar

```python
from fastapi import APIRouter, Depends, HTTPException

from ingestao import odoo_cliente

from .auth import verificar_token
from .odoo import get_cliente_servico
```

por

```python
from fastapi import APIRouter, Depends, HTTPException

from ingestao import odoo_cliente

from .auth import get_cliente_usuario, verificar_token
```

E trocar `cliente=Depends(get_cliente_servico)` por `cliente=Depends(get_cliente_usuario)` na rota `get_alarmes`.

- [ ] **Step 8: Rodar `test_meta.py` e `test_alarmes.py` completos e confirmar que passam**

Run: `python3 -m pytest api/tests/test_meta.py api/tests/test_alarmes.py -v`
Expected: 20 passed (9 de `test_meta.py` + 11 de `test_alarmes.py`).

- [ ] **Step 9: Commit**

```bash
git add api/tests/tenant_fixtures.py api/meta.py api/alarmes.py api/tests/test_meta.py api/tests/test_alarmes.py
git commit -m "feat: meta e alarmes usam sessao real do usuario (ir.rule filtra por tenant)"
```

---

## Task 3: `api/permissions.py` (sites permitidos) + filtro obrigatório no TimescaleDB

**Files:**
- Create: `api/permissions.py`
- Create: `api/tests/test_permissions.py`
- Modify: `api/timescale.py`
- Modify: `api/historico.py`
- Modify: `api/tests/test_timescale.py`
- Modify: `api/tests/test_historico.py`

**Interfaces:**
- Consumes: `api.auth.get_cliente_usuario` (Task 1); `api.tests.tenant_fixtures.criar_tenant`/`remover_tenant` (Task 2); `ingestao.odoo_cliente.executar`; `ingestao.timescale.conectar`.
- Produces: `api.permissions.obter_sites_permitidos(cliente) -> list[str]` — usado pela Task 4.

**Nota de arquitetura:** `sensor_reading` (tabela raw) tem coluna `site_id`, mas as views agregadas contínuas (`sensor_reading_hourly`, `sensor_reading_daily`, ver `timescale/init.sql`) são agrupadas só por `sensor_id`/`bucket` — não têm `site_id`. Recriar essas views pra adicionar a coluna é uma migração maior (drop/recreate de continuous aggregate, com risco pra dado já acumulado) e fica fora deste plano. Para `buscar_agregado`, a checagem de tenant é feita consultando o `site_id` daquele `sensor_code` direto na tabela raw (uma linha, indexada por `idx_sensor_reading_sensor_time`) antes de consultar a view agregada — mesmo efeito estrutural, sem migração.

- [ ] **Step 1: Escrever o teste em `api/tests/test_permissions.py`**

```python
from api.odoo import ODOO_DB, ODOO_URL, get_cliente_servico
from api.permissions import obter_sites_permitidos
from api.tests.tenant_fixtures import criar_tenant, remover_tenant
from ingestao import odoo_cliente


def test_servico_admin_ve_todos_os_sites():
    cliente = get_cliente_servico()
    sites = obter_sites_permitidos(cliente)
    assert len(sites) >= 3
    assert 'SITE-SIM-0001' in sites


def test_usuario_tenant_ve_apenas_o_proprio_site():
    tenant_a = criar_tenant('PERM-A')
    tenant_b = criar_tenant('PERM-B')
    try:
        cliente_a = odoo_cliente.conectar(ODOO_URL, ODOO_DB, tenant_a['login'], tenant_a['senha'])
        sites = obter_sites_permitidos(cliente_a)
        assert sites == [tenant_a['site_code']]
        assert tenant_b['site_code'] not in sites
    finally:
        remover_tenant(tenant_a)
        remover_tenant(tenant_b)
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `python3 -m pytest api/tests/test_permissions.py -v`
Expected: `ModuleNotFoundError: No module named 'api.permissions'`.

- [ ] **Step 3: Criar `api/permissions.py`**

```python
from ingestao import odoo_cliente


def obter_sites_permitidos(cliente):
    sites = odoo_cliente.executar(cliente, 'sensor_monitor.site', 'search_read', [], fields=['site_code'])
    return [s['site_code'] for s in sites]
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

Run: `python3 -m pytest api/tests/test_permissions.py -v`
Expected: 2 passed.

- [ ] **Step 5: Escrever os testes de filtro em `api/tests/test_timescale.py`** — substituir todo o conteúdo do arquivo por:

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

        pontos = api_timescale.buscar_raw(conn, SENSOR_CODE_TESTE, agora - timedelta(hours=1), ['SITE-TEST'])
        assert len(pontos) == 1
        assert pontos[0]['valor'] == 21.5
    finally:
        _limpar()
        conn.close()


def test_buscar_raw_nao_retorna_leitura_de_site_nao_permitido():
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
                    agora - timedelta(minutes=10), 'SITE-NAO-PERMITIDO', 'COL-TEST', SENSOR_CODE_TESTE,
                    'AREA-TEST', 'temperatura', 21.5, 'C', '4-20ma', 'ok',
                ),
            )
        conn.commit()

        pontos = api_timescale.buscar_raw(conn, SENSOR_CODE_TESTE, agora - timedelta(hours=1), ['SITE-OUTRO'])
        assert pontos == []
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
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "CALL refresh_continuous_aggregate('sensor_reading_hourly', %s, %s)",
                (agora - timedelta(hours=2), agora + timedelta(hours=1)),
            )
        conn.autocommit = False

        pontos = api_timescale.buscar_agregado(
            conn, SENSOR_CODE_TESTE, 'sensor_reading_hourly', agora - timedelta(hours=2), ['SITE-TEST'],
        )
        assert len(pontos) == 1
        assert pontos[0]['avg'] == 21.5
    finally:
        _limpar()
        conn.close()


def test_buscar_agregado_nao_retorna_bucket_de_site_nao_permitido():
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
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "CALL refresh_continuous_aggregate('sensor_reading_hourly', %s, %s)",
                (agora - timedelta(hours=2), agora + timedelta(hours=1)),
            )
        conn.autocommit = False

        pontos = api_timescale.buscar_agregado(
            conn, SENSOR_CODE_TESTE, 'sensor_reading_hourly', agora - timedelta(hours=2), ['SITE-OUTRO'],
        )
        assert pontos == []
    finally:
        _limpar()
        conn.close()
```

- [ ] **Step 6: Rodar os testes e confirmar que falham**

Run: `python3 -m pytest api/tests/test_timescale.py -v`
Expected: `TypeError: buscar_raw() takes 3 positional arguments but 4 were given` (e o mesmo pra `buscar_agregado`).

- [ ] **Step 7: Modificar `api/timescale.py`** — substituir todo o conteúdo por:

```python
TABELAS_AGREGADO = {'sensor_reading_hourly', 'sensor_reading_daily'}


def buscar_raw(conn, sensor_code, desde, sites_permitidos):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT time, valor FROM sensor_reading "
            "WHERE sensor_id = %s AND time >= %s AND site_id = ANY(%s) ORDER BY time",
            (sensor_code, desde, sites_permitidos),
        )
        linhas = cur.fetchall()
    return [{'time': linha[0], 'valor': linha[1]} for linha in linhas]


def buscar_agregado(conn, sensor_code, tabela, desde, sites_permitidos):
    if tabela not in TABELAS_AGREGADO:
        raise ValueError(f"tabela agregada desconhecida: {tabela}")
    with conn.cursor() as cur:
        cur.execute("SELECT site_id FROM sensor_reading WHERE sensor_id = %s LIMIT 1", (sensor_code,))
        linha_site = cur.fetchone()
    if linha_site is not None and linha_site[0] not in sites_permitidos:
        return []
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT bucket, valor_min, valor_max, valor_avg FROM {tabela} "
            "WHERE sensor_id = %s AND bucket >= %s ORDER BY bucket",
            (sensor_code, desde),
        )
        linhas = cur.fetchall()
    return [{'bucket': linha[0], 'min': linha[1], 'max': linha[2], 'avg': linha[3]} for linha in linhas]
```

- [ ] **Step 8: Rodar `test_timescale.py` e confirmar que passa**

Run: `python3 -m pytest api/tests/test_timescale.py -v`
Expected: 4 passed.

- [ ] **Step 9: Escrever o teste de isolamento em `api/tests/test_historico.py`** — adicionar:

```python
from api.tests.tenant_fixtures import criar_tenant, remover_tenant


def test_historico_sensor_de_outro_tenant_retorna_404():
    tenant_a = criar_tenant('HIST-A')
    tenant_b = criar_tenant('HIST-B')
    try:
        resposta_login = client.post('/auth/login', json={'usuario': tenant_a['login'], 'senha': tenant_a['senha']})
        token = resposta_login.json()['access_token']
        resposta = client.get(
            f"/sensores/{tenant_b['sensor_code']}/historico",
            params={'window': '1h'},
            headers={'Authorization': f'Bearer {token}'},
        )
        assert resposta.status_code == 404
    finally:
        remover_tenant(tenant_a)
        remover_tenant(tenant_b)
```

- [ ] **Step 10: Rodar o teste e confirmar que falha**

Run: `python3 -m pytest api/tests/test_historico.py::test_historico_sensor_de_outro_tenant_retorna_404 -v`
Expected: FAIL — `/sensores/{code}/historico` hoje usa `get_cliente_servico`.

- [ ] **Step 11: Modificar `api/historico.py`** — substituir todo o conteúdo por:

```python
import os
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from ingestao.timescale import conectar

from . import timescale as api_timescale
from .auth import get_cliente_usuario, verificar_token
from .meta import obter_sensor
from .permissions import obter_sites_permitidos

router = APIRouter()

DSN = os.environ.get('TIMESCALE_DSN', 'postgresql://sentinela:sentinela@localhost:5433/sentinela')

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
    cliente=Depends(get_cliente_usuario),
    _claims=Depends(verificar_token),
):
    if obter_sensor(cliente, sensor_code) is None:
        raise HTTPException(status_code=404, detail=f"sensor '{sensor_code}' não encontrado")

    sites_permitidos = obter_sites_permitidos(cliente)
    config = _JANELAS[window]
    desde = datetime.now(timezone.utc) - config['delta']

    conn = conectar(DSN)
    try:
        if config['resolution'] == 'raw':
            linhas = api_timescale.buscar_raw(conn, sensor_code, desde, sites_permitidos)
            points = [{'ts': int(linha['time'].timestamp() * 1000), 'value': linha['valor']} for linha in linhas]
        else:
            linhas = api_timescale.buscar_agregado(conn, sensor_code, config['tabela'], desde, sites_permitidos)
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

- [ ] **Step 12: Rodar `test_historico.py` completo e confirmar que passa**

Run: `python3 -m pytest api/tests/test_permissions.py api/tests/test_timescale.py api/tests/test_historico.py -v`
Expected: 12 passed (2 de `test_permissions.py` + 4 de `test_timescale.py` + 6 de `test_historico.py`).

- [ ] **Step 13: Commit**

```bash
git add api/permissions.py api/timescale.py api/historico.py api/tests/test_permissions.py api/tests/test_timescale.py api/tests/test_historico.py
git commit -m "feat: sites permitidos via Odoo + filtro obrigatorio no Timescale (raw e agregado)"
```

---

## Task 4: Trigger do Postgres inclui `site_id` + SSE filtra por site permitido

**Files:**
- Modify: `timescale/init.sql`
- Modify: `api/live.py`
- Modify: `api/tests/test_live_trigger.py`
- Modify: `api/tests/test_live_listener.py`
- Modify: `api/tests/test_live_registry.py`
- Modify: `api/tests/test_live_endpoint.py`

**Interfaces:**
- Consumes: `api.auth.get_cliente_usuario_query` (Task 1); `api.permissions.obter_sites_permitidos` (Task 3); `api.meta.obter_sensor`; `api.tests.tenant_fixtures.criar_tenant`/`remover_tenant` (Task 2).
- Produces: `api.live.registrar(sensor_code, sites_permitidos) -> Queue`, `api.live.registrar_global(sites_permitidos) -> Queue`, `api.live.publicar(sensor_code, payload)` (assinaturas mudam — consumido só por `api.live_listener`, que já passa o payload adiante sem inspecionar a assinatura).

- [ ] **Step 1: Escrever o teste de trigger em `api/tests/test_live_trigger.py`** — adicionar a asserção de `site_id` ao teste existente:

```python
        payload = json.loads(notificacao.payload)
        assert payload['sensor_id'] == SENSOR_CODE_TESTE
        assert payload['site_id'] == 'SITE-TEST'
        assert payload['valor'] == 23.4
```

(substitui as duas últimas asserções do teste `test_trigger_dispara_notify_no_insert`, que hoje são só `sensor_id` e `valor`.)

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `python3 -m pytest api/tests/test_live_trigger.py -v`
Expected: FAIL — `KeyError: 'site_id'` (o trigger atual não inclui esse campo no payload).

- [ ] **Step 3: Modificar `timescale/init.sql`** — trocar

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
```

por

```sql
CREATE OR REPLACE FUNCTION notify_sensor_reading() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify(
        'sensor_reading_new',
        json_build_object(
            'sensor_id', NEW.sensor_id,
            'site_id', NEW.site_id,
            'time', extract(epoch from NEW.time) * 1000,
            'valor', NEW.valor
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

- [ ] **Step 4: Aplicar a mudança no TimescaleDB já rodando** — `docker-entrypoint-initdb.d` só roda na primeira inicialização do container, então editar `init.sql` sozinho não afeta o container já em execução. Rodar:

```bash
python3 - <<'EOF'
from ingestao.timescale import conectar

DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'
conn = conectar(DSN)
conn.autocommit = True
with conn.cursor() as cur:
    cur.execute("""
        CREATE OR REPLACE FUNCTION notify_sensor_reading() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify(
                'sensor_reading_new',
                json_build_object(
                    'sensor_id', NEW.sensor_id,
                    'site_id', NEW.site_id,
                    'time', extract(epoch from NEW.time) * 1000,
                    'valor', NEW.valor
                )::text
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
conn.close()
print("trigger atualizado")
EOF
```

Expected: imprime `trigger atualizado` sem erro.

- [ ] **Step 5: Rodar o teste do Step 1/2 e confirmar que passa**

Run: `python3 -m pytest api/tests/test_live_trigger.py -v`
Expected: 1 passed.

- [ ] **Step 6: Atualizar `api/tests/test_live_listener.py`** — trocar

```python
        fila = live.registrar(SENSOR_CODE_TESTE)
```

por

```python
        fila = live.registrar(SENSOR_CODE_TESTE, ['SITE-TEST'])
```

e trocar

```python
            item = await asyncio.wait_for(fila.get(), timeout=3)
            assert item['sensor_id'] == SENSOR_CODE_TESTE
            assert item['valor'] == 18.2
```

por

```python
            item = await asyncio.wait_for(fila.get(), timeout=3)
            assert item['sensor_id'] == SENSOR_CODE_TESTE
            assert item['site_id'] == 'SITE-TEST'
            assert item['valor'] == 18.2
```

- [ ] **Step 7: Reescrever `api/tests/test_live_registry.py`** — substituir todo o conteúdo por:

```python
import asyncio

import pytest

from api import live


def test_registrar_e_publicar_entrega_na_fila():
    async def cenario():
        fila = live.registrar('SNR-1', ['SITE-A'])
        live.publicar('SNR-1', {'valor': 1, 'site_id': 'SITE-A'})
        item = await asyncio.wait_for(fila.get(), timeout=1)
        assert item == {'valor': 1, 'site_id': 'SITE-A'}
        live.remover('SNR-1', fila)

    asyncio.run(cenario())


def test_publicar_sem_inscritos_nao_lanca_erro():
    live.publicar('SNR-SEM-INSCRITOS', {'valor': 2, 'site_id': 'SITE-A'})


def test_remover_impede_entrega_futura():
    async def cenario():
        fila = live.registrar('SNR-2', ['SITE-A'])
        live.remover('SNR-2', fila)
        live.publicar('SNR-2', {'valor': 3, 'site_id': 'SITE-A'})
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(fila.get(), timeout=0.2)

    asyncio.run(cenario())


def test_registrar_global_e_publicar_entrega_em_todas_as_filas_globais():
    async def cenario():
        fila = live.registrar_global(['SITE-A'])
        live.publicar('QUALQUER-SENSOR', {'sensor_id': 'QUALQUER-SENSOR', 'site_id': 'SITE-A', 'valor': 42})
        item = await asyncio.wait_for(fila.get(), timeout=1)
        assert item == {'sensor_id': 'QUALQUER-SENSOR', 'site_id': 'SITE-A', 'valor': 42}
        live.remover_global(fila)

    asyncio.run(cenario())


def test_remover_global_impede_entrega_futura():
    async def cenario():
        fila = live.registrar_global(['SITE-A'])
        live.remover_global(fila)
        live.publicar('SNR-X', {'valor': 1, 'site_id': 'SITE-A'})
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(fila.get(), timeout=0.2)

    asyncio.run(cenario())


def test_publicar_alimenta_fila_por_sensor_e_fila_global_ao_mesmo_tempo():
    async def cenario():
        fila_sensor = live.registrar('SNR-Y', ['SITE-Y'])
        fila_global = live.registrar_global(['SITE-Y'])
        live.publicar('SNR-Y', {'sensor_id': 'SNR-Y', 'site_id': 'SITE-Y', 'valor': 7})

        item_sensor = await asyncio.wait_for(fila_sensor.get(), timeout=1)
        item_global = await asyncio.wait_for(fila_global.get(), timeout=1)
        assert item_sensor == item_global == {'sensor_id': 'SNR-Y', 'site_id': 'SITE-Y', 'valor': 7}

        live.remover('SNR-Y', fila_sensor)
        live.remover_global(fila_global)

    asyncio.run(cenario())


def test_publicar_nao_entrega_para_fila_sem_permissao_do_site():
    async def cenario():
        fila = live.registrar_global(['SITE-PERMITIDO'])
        live.publicar('QUALQUER-SENSOR', {'sensor_id': 'QUALQUER-SENSOR', 'site_id': 'SITE-NAO-PERMITIDO', 'valor': 1})
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(fila.get(), timeout=0.2)
        live.remover_global(fila)

    asyncio.run(cenario())
```

- [ ] **Step 8: Atualizar as duas chamadas de `live.publicar` em `api/tests/test_live_endpoint.py`** — trocar

```python
            live.publicar(SENSOR_CODE, {'sensor_id': SENSOR_CODE, 'time': 1700000000000, 'valor': 25.0})
```

por

```python
            live.publicar(SENSOR_CODE, {'sensor_id': SENSOR_CODE, 'site_id': 'SITE-SIM-0001', 'time': 1700000000000, 'valor': 25.0})
```

e trocar

```python
            live.publicar('QUALQUER-OUTRO-SENSOR', {'sensor_id': 'QUALQUER-OUTRO-SENSOR', 'time': 1700000000000, 'valor': 15.0})
```

por

```python
            live.publicar('QUALQUER-OUTRO-SENSOR', {'sensor_id': 'QUALQUER-OUTRO-SENSOR', 'site_id': 'SITE-SIM-0001', 'time': 1700000000000, 'valor': 15.0})
```

(`SITE-SIM-0001` é um site real, já visível pra `admin`/`get_cliente_servico`, usado nesses dois testes.)

- [ ] **Step 9: Escrever o teste de isolamento HTTP em `api/tests/test_live_endpoint.py`** — adicionar:

```python
from api.tests.tenant_fixtures import criar_tenant, remover_tenant


def test_live_sensor_de_outro_tenant_retorna_404():
    tenant_a = criar_tenant('LIVE-A')
    tenant_b = criar_tenant('LIVE-B')
    try:
        client = TestClient(app)
        resposta_login = client.post('/auth/login', json={'usuario': tenant_a['login'], 'senha': tenant_a['senha']})
        token = resposta_login.json()['access_token']
        resposta = client.get(f"/sensores/{tenant_b['sensor_code']}/live", params={'token': token})
        assert resposta.status_code == 404
    finally:
        remover_tenant(tenant_a)
        remover_tenant(tenant_b)
```

- [ ] **Step 10: Rodar `test_live_registry.py` e `test_live_endpoint.py` e confirmar que falham**

Run: `python3 -m pytest api/tests/test_live_registry.py api/tests/test_live_endpoint.py -v`
Expected: FAIL — `TypeError: registrar() missing 1 required positional argument: 'sites_permitidos'` (e equivalente pra `registrar_global`); o teste novo de `/live` cross-tenant também falha (ainda usa `get_cliente_servico`, vê tudo).

- [ ] **Step 11: Modificar `api/live.py`** — substituir todo o conteúdo por:

```python
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from .auth import get_cliente_usuario_query, verificar_token_query
from .meta import obter_sensor
from .permissions import obter_sites_permitidos

router = APIRouter()

_registry: dict[str, set[asyncio.Queue]] = {}
_registry_global: set[asyncio.Queue] = set()
_sites_por_fila: dict[asyncio.Queue, frozenset] = {}


def registrar(sensor_code: str, sites_permitidos) -> asyncio.Queue:
    fila = asyncio.Queue()
    _registry.setdefault(sensor_code, set()).add(fila)
    _sites_por_fila[fila] = frozenset(sites_permitidos)
    return fila


def remover(sensor_code: str, fila: asyncio.Queue) -> None:
    filas = _registry.get(sensor_code)
    if filas is not None:
        filas.discard(fila)
        if not filas:
            _registry.pop(sensor_code, None)
    _sites_por_fila.pop(fila, None)


def registrar_global(sites_permitidos) -> asyncio.Queue:
    fila = asyncio.Queue()
    _registry_global.add(fila)
    _sites_por_fila[fila] = frozenset(sites_permitidos)
    return fila


def remover_global(fila: asyncio.Queue) -> None:
    _registry_global.discard(fila)
    _sites_por_fila.pop(fila, None)


def publicar(sensor_code: str, payload: dict) -> None:
    site_id = payload.get('site_id')
    for fila in _registry.get(sensor_code, ()):
        if site_id in _sites_por_fila.get(fila, frozenset()):
            fila.put_nowait(payload)
    for fila in _registry_global:
        if site_id in _sites_por_fila.get(fila, frozenset()):
            fila.put_nowait(payload)


@router.get('/sensores/{sensor_code}/live')
async def get_live(
    sensor_code: str,
    cliente=Depends(get_cliente_usuario_query),
    _claims=Depends(verificar_token_query),
):
    if await asyncio.to_thread(obter_sensor, cliente, sensor_code) is None:
        raise HTTPException(status_code=404, detail=f"sensor '{sensor_code}' não encontrado")

    sites_permitidos = await asyncio.to_thread(obter_sites_permitidos, cliente)
    fila = registrar(sensor_code, sites_permitidos)

    async def stream():
        try:
            while True:
                payload = await fila.get()
                yield f"data: {json.dumps(payload)}\n\n"
        finally:
            remover(sensor_code, fila)

    return StreamingResponse(stream(), media_type='text/event-stream')


@router.get('/live')
async def get_live_global(
    cliente=Depends(get_cliente_usuario_query),
    _claims=Depends(verificar_token_query),
):
    # Sem sensor_code: multiplexa eventos de TODOS os sensores PERMITIDOS pro
    # usuario numa unica conexao. Existe pra nao estourar o limite de 6
    # conexoes HTTP/1.1 persistentes por origem que os browsers aplicam --
    # com N sensores na tela (dashboard fundido), abrir 1 EventSource por
    # sensor trava os sensores alem do 6o pra sempre (achado em teste real,
    # ver docs/superpowers/plans/2026-07-19-live-sse-backend.md).
    sites_permitidos = await asyncio.to_thread(obter_sites_permitidos, cliente)
    fila = registrar_global(sites_permitidos)

    async def stream():
        try:
            while True:
                payload = await fila.get()
                yield f"data: {json.dumps(payload)}\n\n"
        finally:
            remover_global(fila)

    return StreamingResponse(stream(), media_type='text/event-stream')
```

(`get_live` já tinha parâmetro `cliente` antes — a chamada direta `live.get_live(SENSOR_CODE, cliente=cliente, _claims={})` em `test_live_endpoint.py` continua funcionando sem alteração. `get_live_global` **ganhou** o parâmetro `cliente`, que não existia antes — a chamada direta `live.get_live_global(_claims={})` precisa ser atualizada para passar esse argumento; ver Step 12.)

- [ ] **Step 12: Atualizar a chamada direta de `get_live_global` em `api/tests/test_live_endpoint.py`** — trocar

```python
        resposta = await live.get_live_global(_claims={})
```

por

```python
        resposta = await live.get_live_global(cliente=get_cliente_servico(), _claims={})
```

- [ ] **Step 13: Rodar `test_live_trigger.py`, `test_live_listener.py`, `test_live_registry.py` e `test_live_endpoint.py` e confirmar que passam**

Run: `python3 -m pytest api/tests/test_live_trigger.py api/tests/test_live_listener.py api/tests/test_live_registry.py api/tests/test_live_endpoint.py -v`
Expected: 17 passed (1 + 1 + 7 + 8).

- [ ] **Step 14: Commit**

```bash
git add timescale/init.sql api/live.py api/tests/test_live_trigger.py api/tests/test_live_listener.py api/tests/test_live_registry.py api/tests/test_live_endpoint.py
git commit -m "feat: trigger Timescale inclui site_id + SSE filtra publicacao por site permitido"
```

---

## Task 5: Verificação final — suíte completa + servidor real + prova manual de isolamento cross-tenant

**Files:**
- Modify: nenhum arquivo novo — task de verificação/fechamento.

**Interfaces:**
- Consumes: tudo das Tasks 1–4.

- [ ] **Step 1: Rodar a suíte completa**

Run (a partir da raiz do repo): `python3 -m pytest api/tests/ -v`
Expected: 72 passed (55 já existentes + 4 `test_sessions` + 3 novos em `test_auth` + 2 novos em `test_meta` + 1 novo em `test_alarmes` + 2 `test_permissions` (novo) + 2 novos em `test_timescale` + 1 novo em `test_historico` + 1 novo em `test_live_registry` + 1 novo em `test_live_endpoint`).

- [ ] **Step 2: Subir o servidor de verdade e provar isolamento cross-tenant end-to-end com curl**

Run:
```bash
python3 -m uvicorn api.main:app --port 8001 &
sleep 2

python3 - <<'EOF'
from api.tests.tenant_fixtures import criar_tenant
import json

tenant_a = criar_tenant('E2E-A')
tenant_b = criar_tenant('E2E-B')
with open('/tmp/tenant_a.json', 'w') as f:
    json.dump(tenant_a, f)
with open('/tmp/tenant_b.json', 'w') as f:
    json.dump(tenant_b, f)
print(tenant_a['login'], tenant_a['sensor_code'])
print(tenant_b['login'], tenant_b['sensor_code'])
EOF

LOGIN_A=$(python3 -c "import json; print(json.load(open('/tmp/tenant_a.json'))['login'])")
SENSOR_B=$(python3 -c "import json; print(json.load(open('/tmp/tenant_b.json'))['sensor_code'])")

TOKEN_A=$(curl -s -X POST http://localhost:8001/auth/login -H "Content-Type: application/json" \
  -d "{\"usuario\":\"$LOGIN_A\",\"senha\":\"senha-teste-tenant-123\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "--- /sensores como tenant A (esperado: NAO conter $SENSOR_B) ---"
curl -s http://localhost:8001/sensores -H "Authorization: Bearer $TOKEN_A" | python3 -m json.tool

echo "--- /sensores/$SENSOR_B como tenant A (esperado: 404) ---"
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8001/sensores/$SENSOR_B" -H "Authorization: Bearer $TOKEN_A"

echo "--- /sensores/$SENSOR_B/historico como tenant A (esperado: 404) ---"
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8001/sensores/$SENSOR_B/historico?window=1h" -H "Authorization: Bearer $TOKEN_A"

python3 - <<'EOF'
from api.tests.tenant_fixtures import remover_tenant
import json

remover_tenant(json.load(open('/tmp/tenant_a.json')))
remover_tenant(json.load(open('/tmp/tenant_b.json')))
EOF
rm -f /tmp/tenant_a.json /tmp/tenant_b.json

kill %1
```
Expected: lista de `/sensores` pro tenant A não contém o `sensor_code` do tenant B; ambos os `curl -o /dev/null -w "%{http_code}"` imprimem `404`.

- [ ] **Step 3: Confirmar que o fluxo de um único tenant continua funcionando (sem regressão no caminho feliz)**

Run:
```bash
python3 -m uvicorn api.main:app --port 8001 &
sleep 2
TOKEN=$(curl -s -X POST http://localhost:8001/auth/login -H "Content-Type: application/json" -d '{"usuario":"admin","senha":"admin"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
curl -s http://localhost:8001/sensores -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
curl -s http://localhost:8001/sensores/SNR-SIM-TEMP-01 -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
curl -s "http://localhost:8001/sensores/SNR-SIM-TEMP-01/historico?window=1h" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
kill %1
```
Expected: lista de sensores inclui `TEMP-01`/`SNR-SIM-TEMP-01`/`SNR-SIM-PRES-01` (admin vê tudo, como já era); objeto `SensorMeta` completo; histórico responde 200 com `points` (lista, possivelmente vazia se não há leituras recentes).

- [ ] **Step 4: Confirmar que subir a API sem `API_JWT_SECRET` falha**

Run: `env -u API_JWT_SECRET python3 -c "import api.auth"`
Expected: `RuntimeError: API_JWT_SECRET não definido...` e código de saída != 0.

- [ ] **Step 5: Commit final**

```bash
git add -A
git commit -m "chore: verificacao final do isolamento multi-tenant na API" --allow-empty
```
