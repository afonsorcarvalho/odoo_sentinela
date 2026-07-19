# Configuração do Dashboard via Odoo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Intervalo do carrossel de sensores no `AreaCard` deixa de ser hardcoded (`3000ms`) e passa a vir do Odoo, por site, através de um mecanismo geral de configuração de dashboard (`sensor_monitor.dashboard.config` → `GET /config` → `useConfig()` → prop `carouselIntervalMs`).

**Architecture:** 3 camadas, cada uma testável isoladamente: (1) modelo Odoo novo `sensor_monitor.dashboard.config`, 1-pra-1 com `sensor_monitor.site`; (2) endpoint FastAPI `GET /config` que resolve o site via env var e busca a config (ou default, se não existir registro); (3) frontend consome via `ConfigApi`/`useConfig()` (mesmo padrão de `MetaApi`/`useSensors()`) e repassa o valor pro `AreaCard` via prop.

**Tech Stack:** Odoo 18 (Python), FastAPI, React 19 + TS + Vitest + TanStack Query.

## Global Constraints

- Resolução de site na API é via env var `SENTINELA_SITE_CODE` (`os.environ.get('SENTINELA_SITE_CODE', 'SITE-DEMO-01')` em `api/odoo.py`) — 1 deployment = 1 site, mesmo padrão de `ODOO_DB`/`ODOO_URL`. Não implementar site_code por request/header — fora de escopo.
- `carousel_interval_ms` tem piso de **1000ms** (constraint Odoo) — valor abaixo disso é inválido.
- `unique(site_id)` — no máximo 1 `dashboard.config` por site.
- Sem registro de config para o site: `GET /config` retorna o default (`carousel_interval_ms: 3000`), **não** é erro 404.
- Sem auto-criação de `dashboard.config` ao criar um site — registro só existe quando criado explicitamente.
- `AreaCard`'s prop `carouselIntervalMs` é **obrigatória** (sem valor default no componente) — quem decide o fallback pra 3000 é o `DashboardPage`, via `config.data?.carousel_interval_ms ?? 3000`, não o `AreaCard`.
- Sem dependência nova (nem Python nem npm).
- Autenticação de `/config`: mesmo `verificar_token` (JWT) dos outros endpoints — não é rota pública.
- Segurança Odoo do novo modelo: mesmos grupos/regras já usados por `sensor_monitor.site` (`group_sensor_monitor_view` leitura, `group_sensor_monitor_admin` CRUD completo, isolamento por `partner_id` via `ir.rule`).

---

### Task 1: Modelo Odoo `sensor_monitor.dashboard.config`

**Files:**
- Create: `addons/afr_sentinela_sensor_monitor/models/dashboard_config.py`
- Modify: `addons/afr_sentinela_sensor_monitor/models/__init__.py`
- Create: `addons/afr_sentinela_sensor_monitor/views/dashboard_config_views.xml`
- Modify: `addons/afr_sentinela_sensor_monitor/views/menu.xml`
- Modify: `addons/afr_sentinela_sensor_monitor/security/ir.model.access.csv`
- Modify: `addons/afr_sentinela_sensor_monitor/security/security_rules.xml`
- Modify: `addons/afr_sentinela_sensor_monitor/__manifest__.py`
- Create: `addons/afr_sentinela_sensor_monitor/tests/test_dashboard_config.py`
- Modify: `addons/afr_sentinela_sensor_monitor/tests/__init__.py`

**Interfaces:**
- Produces: modelo Odoo `sensor_monitor.dashboard.config` com campos `site_id` (Many2one `sensor_monitor.site`) e `carousel_interval_ms` (Integer, default 3000). Task 2 vai ler esse modelo via `odoo_cliente.executar(cliente, 'sensor_monitor.dashboard.config', 'search_read', [('site_id', '=', <id>)], fields=['carousel_interval_ms'])`.

- [ ] **Step 1: Escrever o teste falho do modelo**

Criar `addons/afr_sentinela_sensor_monitor/tests/test_dashboard_config.py`:

```python
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestDashboardConfig(TransactionCase):

    def setUp(self):
        super().setUp()
        partner = self.env['res.partner'].create({'name': 'Hospital Teste'})
        self.site = self.env['sensor_monitor.site'].create({
            'name': 'CME Central',
            'partner_id': partner.id,
            'site_code': 'SITE-020',
            'vertical': 'cme_hospitalar',
        })

    def test_cria_config_associada_ao_site(self):
        config = self.env['sensor_monitor.dashboard.config'].create({
            'site_id': self.site.id,
            'carousel_interval_ms': 5000,
        })
        self.assertEqual(config.site_id, self.site)
        self.assertEqual(config.carousel_interval_ms, 5000)

    def test_default_carousel_interval_ms_e_3000(self):
        config = self.env['sensor_monitor.dashboard.config'].create({'site_id': self.site.id})
        self.assertEqual(config.carousel_interval_ms, 3000)

    def test_site_id_unico_impede_segunda_config_no_mesmo_site(self):
        self.env['sensor_monitor.dashboard.config'].create({'site_id': self.site.id})
        with self.assertRaises(Exception):
            self.env['sensor_monitor.dashboard.config'].create({'site_id': self.site.id})

    def test_carousel_interval_ms_abaixo_do_piso_falha(self):
        with self.assertRaises(ValidationError):
            self.env['sensor_monitor.dashboard.config'].create({
                'site_id': self.site.id,
                'carousel_interval_ms': 500,
            })
```

Registrar em `addons/afr_sentinela_sensor_monitor/tests/__init__.py` — arquivo atual completo:

```python
from . import test_reference_data
from . import test_core_hierarchy
from . import test_alarm_threshold
from . import test_alarm_event
from . import test_file_ledger
from . import test_rs485_modbus
from . import test_security_rules
```

Adicionar uma linha ao final:

```python
from . import test_dashboard_config
```

- [ ] **Step 2: Rodar os testes, confirmar que falham (modelo não existe)**

Run: `docker compose exec odoo odoo -d sentinela --db_host=db --db_user=odoo --db_password=odoo -u afr_sentinela_sensor_monitor --test-enable --stop-after-init --test-tags /afr_sentinela_sensor_monitor`
Expected: FAIL — `KeyError: 'sensor_monitor.dashboard.config'` ou erro equivalente de modelo inexistente.

- [ ] **Step 3: Criar o modelo**

Criar `addons/afr_sentinela_sensor_monitor/models/dashboard_config.py`:

```python
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DashboardConfig(models.Model):
    _name = 'sensor_monitor.dashboard.config'
    _description = 'Configuração do Dashboard'

    site_id = fields.Many2one('sensor_monitor.site', required=True, ondelete='cascade')
    carousel_interval_ms = fields.Integer(
        default=3000, required=True, string='Intervalo do carrossel (ms)',
    )

    _sql_constraints = [
        ('site_id_unique', 'unique(site_id)', 'Já existe uma configuração de dashboard para este site.'),
    ]

    @api.constrains('carousel_interval_ms')
    def _check_carousel_interval_floor(self):
        for config in self:
            if config.carousel_interval_ms < 1000:
                raise ValidationError(
                    'carousel_interval_ms não pode ser menor que 1000 (piso de legibilidade).'
                )
```

Modificar `addons/afr_sentinela_sensor_monitor/models/__init__.py` — arquivo atual completo:

```python
from . import common
from . import area_category
from . import measurement_type
from . import site
from . import area
from . import hub
from . import coletor
from . import sensor
from . import alarm_threshold
from . import alarm_event
from . import file_ledger
from . import rs485_bus
from . import modbus_profile
from . import modbus_device
from . import sensor_rs485_ext
```

Adicionar `from . import dashboard_config` logo após `from . import site`:

```python
from . import common
from . import area_category
from . import measurement_type
from . import site
from . import dashboard_config
from . import area
from . import hub
from . import coletor
from . import sensor
from . import alarm_threshold
from . import alarm_event
from . import file_ledger
from . import rs485_bus
from . import modbus_profile
from . import modbus_device
from . import sensor_rs485_ext
```

- [ ] **Step 4: Views, menu, segurança e manifest**

Criar `addons/afr_sentinela_sensor_monitor/views/dashboard_config_views.xml`:

```xml
<odoo>
    <record id="view_dashboard_config_list" model="ir.ui.view">
        <field name="name">sensor_monitor.dashboard.config.list</field>
        <field name="model">sensor_monitor.dashboard.config</field>
        <field name="arch" type="xml">
            <list>
                <field name="site_id"/>
                <field name="carousel_interval_ms"/>
            </list>
        </field>
    </record>
    <record id="view_dashboard_config_form" model="ir.ui.view">
        <field name="name">sensor_monitor.dashboard.config.form</field>
        <field name="model">sensor_monitor.dashboard.config</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <group>
                        <field name="site_id"/>
                        <field name="carousel_interval_ms"/>
                    </group>
                </sheet>
            </form>
        </field>
    </record>
    <record id="action_dashboard_config" model="ir.actions.act_window">
        <field name="name">Configuração do Dashboard</field>
        <field name="res_model">sensor_monitor.dashboard.config</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

Modificar `addons/afr_sentinela_sensor_monitor/views/menu.xml` — adicionar, logo após a linha do `menu_site` (dentro de `menu_sensor_monitor_cadastro`):

```xml
    <menuitem id="menu_dashboard_config" name="Configuração do Dashboard" parent="menu_sensor_monitor_cadastro" action="action_dashboard_config" sequence="15"/>
```

Modificar `addons/afr_sentinela_sensor_monitor/security/ir.model.access.csv` — adicionar 2 linhas (mesmo padrão de `access_site_view`/`access_site_admin`):

```csv
access_dashboard_config_view,dashboard.config.view,model_sensor_monitor_dashboard_config,group_sensor_monitor_view,1,0,0,0
access_dashboard_config_admin,dashboard.config.admin,model_sensor_monitor_dashboard_config,group_sensor_monitor_admin,1,1,1,1
```

Modificar `addons/afr_sentinela_sensor_monitor/security/security_rules.xml` — adicionar, logo após o bloco `rule_site_admin` (mesmo padrão de `rule_area_tenant`/`rule_area_admin`, mas resolvendo `partner_id` direto via `site_id`):

```xml
    <record id="rule_dashboard_config_tenant" model="ir.rule">
        <field name="name">Config de dashboard: isolamento por cliente</field>
        <field name="model_id" ref="model_sensor_monitor_dashboard_config"/>
        <field name="domain_force">[('site_id.partner_id', '=', user.partner_id.commercial_partner_id.id)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_view')), (4, ref('group_sensor_monitor_operation')), (4, ref('group_sensor_monitor_advanced_config'))]"/>
    </record>
    <record id="rule_dashboard_config_admin" model="ir.rule">
        <field name="name">Config de dashboard: admin vê tudo</field>
        <field name="model_id" ref="model_sensor_monitor_dashboard_config"/>
        <field name="domain_force">[(1, '=', 1)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_admin'))]"/>
    </record>
```

Modificar `addons/afr_sentinela_sensor_monitor/__manifest__.py` — no campo `data`, adicionar `'views/dashboard_config_views.xml',` logo após `'views/site_views.xml',`:

```python
    'data': [
        'security/security_rules.xml',
        'security/ir.model.access.csv',
        'data/area_category_data.xml',
        'data/measurement_type_data.xml',
        'data/file_ledger_cron_data.xml',
        'views/site_views.xml',
        'views/dashboard_config_views.xml',
        'views/area_views.xml',
        'views/hub_views.xml',
        'views/coletor_views.xml',
        'views/sensor_views.xml',
        'views/alarm_threshold_views.xml',
        'views/alarm_event_views.xml',
        'views/file_ledger_views.xml',
        'views/rs485_modbus_views.xml',
        'views/menu.xml',
    ],
```

- [ ] **Step 5: Rodar os testes, confirmar que passam**

Run: `docker compose exec odoo odoo -d sentinela --db_host=db --db_user=odoo --db_password=odoo -u afr_sentinela_sensor_monitor --test-enable --stop-after-init --test-tags /afr_sentinela_sensor_monitor`
Expected: PASS em todos os testes do módulo, incluindo os 4 novos de `test_dashboard_config.py`. Esse mesmo comando também faz o *upgrade* do módulo na base `sentinela` usada pela API (`ODOO_DB=sentinela` em `api/odoo.py`) — depois deste passo o modelo `sensor_monitor.dashboard.config` já existe na base usada pelos testes da Task 2.

- [ ] **Step 6: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor/models/dashboard_config.py \
        addons/afr_sentinela_sensor_monitor/models/__init__.py \
        addons/afr_sentinela_sensor_monitor/views/dashboard_config_views.xml \
        addons/afr_sentinela_sensor_monitor/views/menu.xml \
        addons/afr_sentinela_sensor_monitor/security/ir.model.access.csv \
        addons/afr_sentinela_sensor_monitor/security/security_rules.xml \
        addons/afr_sentinela_sensor_monitor/__manifest__.py \
        addons/afr_sentinela_sensor_monitor/tests/test_dashboard_config.py \
        addons/afr_sentinela_sensor_monitor/tests/__init__.py
git commit -m "feat: modelo sensor_monitor.dashboard.config (config de dashboard por site)"
```

---

### Task 2: API `GET /config`

**Files:**
- Modify: `api/odoo.py`
- Create: `api/config.py`
- Modify: `api/main.py`
- Create: `api/tests/test_config.py`

**Interfaces:**
- Consumes: modelo Odoo `sensor_monitor.dashboard.config` (Task 1, já mesclado na base `sentinela`) e `sensor_monitor.site` (já existente).
- Consumes: `get_cliente_servico()` e `verificar_token` (já existentes, mesmo padrão de `api/meta.py`).
- Produces: `GET /config` → `{"carousel_interval_ms": <int>}`. Task 3 (frontend) consome essa rota via `authFetchJson('/config')`.

- [ ] **Step 1: Adicionar `SITE_CODE` em `api/odoo.py`**

Arquivo atual completo:

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

Substituir por:

```python
import os
from functools import lru_cache

from ingestao import odoo_cliente

ODOO_URL = os.environ.get('ODOO_URL', 'http://localhost:8189')
ODOO_DB = os.environ.get('ODOO_DB', 'sentinela')
ODOO_USUARIO_SERVICO = os.environ.get('ODOO_USUARIO_SERVICO', 'admin')
ODOO_SENHA_SERVICO = os.environ.get('ODOO_SENHA_SERVICO', 'admin')
SITE_CODE = os.environ.get('SENTINELA_SITE_CODE', 'SITE-DEMO-01')


@lru_cache
def get_cliente_servico():
    return odoo_cliente.conectar(ODOO_URL, ODOO_DB, ODOO_USUARIO_SERVICO, ODOO_SENHA_SERVICO)
```

- [ ] **Step 2: Escrever o teste falho da rota**

Criar `api/tests/test_config.py`:

```python
from fastapi.testclient import TestClient

from api.main import app
from api.odoo import SITE_CODE, get_cliente_servico
from ingestao import odoo_cliente

client = TestClient(app)


def _headers():
    resposta = client.post('/auth/login', json={'usuario': 'admin', 'senha': 'admin'})
    token = resposta.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def _site_id(cliente):
    sites = odoo_cliente.executar(
        cliente, 'sensor_monitor.site', 'search_read',
        [('site_code', '=', SITE_CODE)], fields=['id'],
    )
    if sites:
        return sites[0]['id']
    partner_ids = odoo_cliente.executar(cliente, 'res.partner', 'search', [], limit=1)
    return odoo_cliente.executar(
        cliente, 'sensor_monitor.site', 'create',
        {
            'name': 'Site de teste config',
            'partner_id': partner_ids[0],
            'site_code': SITE_CODE,
            'vertical': 'cme_hospitalar',
        },
    )


def test_config_sem_token_retorna_401():
    resposta = client.get('/config')
    assert resposta.status_code == 401


def test_config_sem_registro_retorna_default():
    cliente = get_cliente_servico()
    site_id = _site_id(cliente)
    configs_existentes = odoo_cliente.executar(
        cliente, 'sensor_monitor.dashboard.config', 'search', [('site_id', '=', site_id)],
    )
    if configs_existentes:
        odoo_cliente.executar(cliente, 'sensor_monitor.dashboard.config', 'unlink', configs_existentes)

    resposta = client.get('/config', headers=_headers())

    assert resposta.status_code == 200
    assert resposta.json() == {'carousel_interval_ms': 3000}


def test_config_com_registro_retorna_valor_configurado():
    cliente = get_cliente_servico()
    site_id = _site_id(cliente)
    config_id = odoo_cliente.executar(
        cliente, 'sensor_monitor.dashboard.config', 'create',
        {'site_id': site_id, 'carousel_interval_ms': 7000},
    )
    try:
        resposta = client.get('/config', headers=_headers())
        assert resposta.status_code == 200
        assert resposta.json() == {'carousel_interval_ms': 7000}
    finally:
        odoo_cliente.executar(cliente, 'sensor_monitor.dashboard.config', 'unlink', [config_id])
```

- [ ] **Step 3: Rodar os testes, confirmar que falham (rota não existe)**

Run: `cd /home/afonso/docker/odoo_sentinela && python3 -m pytest api/tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.config'` ou 404 em `/config`.

- [ ] **Step 4: Implementar a rota**

Criar `api/config.py`:

```python
from fastapi import APIRouter, Depends

from ingestao import odoo_cliente

from .auth import verificar_token
from .odoo import SITE_CODE, get_cliente_servico

router = APIRouter()

_DEFAULT_CAROUSEL_INTERVAL_MS = 3000


def obter_config(cliente):
    sites = odoo_cliente.executar(
        cliente, 'sensor_monitor.site', 'search_read',
        [('site_code', '=', SITE_CODE)], fields=['id'],
    )
    if not sites:
        return {'carousel_interval_ms': _DEFAULT_CAROUSEL_INTERVAL_MS}

    configs = odoo_cliente.executar(
        cliente, 'sensor_monitor.dashboard.config', 'search_read',
        [('site_id', '=', sites[0]['id'])], fields=['carousel_interval_ms'],
    )
    if not configs:
        return {'carousel_interval_ms': _DEFAULT_CAROUSEL_INTERVAL_MS}

    return {'carousel_interval_ms': configs[0]['carousel_interval_ms']}


@router.get('/config')
def get_config(cliente=Depends(get_cliente_servico), _claims=Depends(verificar_token)):
    return obter_config(cliente)
```

Modificar `api/main.py` — trocar:

```python
from . import alarmes, auth, historico, live, live_listener, meta
```

por:

```python
from . import alarmes, auth, config, historico, live, live_listener, meta
```

e, no bloco de `include_router`, adicionar `app.include_router(config.router)` (mesmo padrão dos demais):

```python
app.include_router(alarmes.router)
app.include_router(auth.router)
app.include_router(config.router)
app.include_router(meta.router)
app.include_router(historico.router)
app.include_router(live.router)
```

- [ ] **Step 5: Rodar os testes, confirmar que passam**

Run: `cd /home/afonso/docker/odoo_sentinela && python3 -m pytest api/tests/test_config.py -v`
Expected: PASS nos 3 testes.

- [ ] **Step 6: Rodar a suite inteira da API, confirmar que nada quebrou**

Run: `cd /home/afonso/docker/odoo_sentinela && python3 -m pytest api/tests/ -v`
Expected: PASS em todos os arquivos (o servidor Odoo/API precisa estar de pé — `docker compose ps` deve mostrar `odoo`/`db`/`timescaledb` `Up`).

- [ ] **Step 7: Commit**

```bash
git add api/odoo.py api/config.py api/main.py api/tests/test_config.py
git commit -m "feat: endpoint GET /config (intervalo do carrossel por site)"
```

---

### Task 3: Frontend consome `/config` e alimenta o `AreaCard`

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api/contracts.ts`
- Create: `frontend/src/lib/api/mock/configApi.ts`
- Create: `frontend/src/lib/api/real/configApi.ts`
- Create: `frontend/src/lib/api/real/configApi.test.ts`
- Modify: `frontend/src/lib/api/index.ts`
- Modify: `frontend/src/lib/api/index.test.ts`
- Modify: `frontend/src/lib/queries.ts`
- Modify: `frontend/src/lib/queries.test.tsx`
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/components/AreaCard.tsx`
- Modify: `frontend/src/components/AreaCard.test.tsx`

**Interfaces:**
- Consumes: `GET /config` (Task 2) via `authFetchJson('/config')`.
- Produces: `AreaCard` ganha prop obrigatória nova `carouselIntervalMs: number`, repassada pro `useSensorCarousel(group.sensors.length, carouselIntervalMs)` (assinatura do hook, de uma feature anterior, não muda).

- [ ] **Step 1: Tipo `DashboardConfig`**

Modificar `frontend/src/lib/types.ts` — adicionar, logo após o tipo `Threshold` (linhas 12-17):

```typescript
export type Threshold = {
  sensor_id: string
  limite_min: number
  limite_max: number
  is_valor_padrao_regulatorio: boolean
}

export type DashboardConfig = {
  carousel_interval_ms: number
}
```

- [ ] **Step 2: Contrato + mock + real + wiring no barrel**

Modificar `frontend/src/lib/api/contracts.ts` — arquivo atual completo:

```typescript
import type { SensorMeta, Threshold, HistoryResponse, LivePoint, Window, AlarmEvent } from '../types'

export type MetaApi = {
  getSensor(code: string): Promise<SensorMeta>
  getThreshold(code: string): Promise<Threshold | null>
  listSensors(): Promise<SensorMeta[]>
}
export type HistoryApi = {
  getHistory(code: string, window: Window): Promise<HistoryResponse>
}
export type LiveApi = {
  subscribe(code: string, cb: (p: LivePoint) => void): () => void
}

export type AuthApi = {
  login(usuario: string, senha: string): Promise<{ access_token: string; token_type: string }>
}
export type AlarmApi = {
  listAlarms(): Promise<AlarmEvent[]>
}
```

Substituir por (import de `DashboardConfig` + `ConfigApi` novo no final):

```typescript
import type { SensorMeta, Threshold, HistoryResponse, LivePoint, Window, AlarmEvent, DashboardConfig } from '../types'

export type MetaApi = {
  getSensor(code: string): Promise<SensorMeta>
  getThreshold(code: string): Promise<Threshold | null>
  listSensors(): Promise<SensorMeta[]>
}
export type HistoryApi = {
  getHistory(code: string, window: Window): Promise<HistoryResponse>
}
export type LiveApi = {
  subscribe(code: string, cb: (p: LivePoint) => void): () => void
}

export type AuthApi = {
  login(usuario: string, senha: string): Promise<{ access_token: string; token_type: string }>
}
export type AlarmApi = {
  listAlarms(): Promise<AlarmEvent[]>
}
export type ConfigApi = {
  getConfig(): Promise<DashboardConfig>
}
```

Criar `frontend/src/lib/api/mock/configApi.ts`:

```typescript
import type { ConfigApi } from '../contracts'

export const mockConfigApi: ConfigApi = {
  async getConfig() {
    return { carousel_interval_ms: 3000 }
  },
}
```

Criar `frontend/src/lib/api/real/configApi.ts`:

```typescript
import type { ConfigApi } from '../contracts'
import { authFetchJson } from './http'

export const realConfigApi: ConfigApi = {
  getConfig() {
    return authFetchJson('/config')
  },
}
```

Criar `frontend/src/lib/api/real/configApi.test.ts` (mesmo padrão de `real/metaApi.test.ts`):

```typescript
import { describe, it, expect, vi, afterEach } from 'vitest'
import { realConfigApi } from './configApi'

afterEach(() => vi.unstubAllGlobals())

describe('realConfigApi', () => {
  it('getConfig chama GET /config e devolve o JSON', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ carousel_interval_ms: 7000 }) })
    vi.stubGlobal('fetch', mockFetch)

    const result = await realConfigApi.getConfig()

    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/config'), expect.anything())
    expect(result).toEqual({ carousel_interval_ms: 7000 })
  })
})
```

Modificar `frontend/src/lib/api/index.ts` — arquivo atual completo:

```typescript
import type { MetaApi, HistoryApi, LiveApi, AuthApi, AlarmApi } from './contracts'
import { mockMetaApi } from './mock/metaApi'
import { mockHistoryApi } from './mock/historyApi'
import { mockLiveApi } from './mock/liveApi'
import { mockAuthApi } from './mock/authApi'
import { mockAlarmApi } from './mock/alarmApi'
import { realAuthApi } from './real/authApi'
import { realMetaApi } from './real/metaApi'
import { realHistoryApi } from './real/historyApi'
import { realLiveApi } from './real/liveApi'
import { realAlarmApi } from './real/alarmApi'

const mode = import.meta.env.VITE_API_MODE ?? 'mock'
if (mode !== 'real' && mode !== 'mock') {
  console.warn(`VITE_API_MODE=${mode} nao reconhecido; usando mock para todos os adapters`)
}

const useReal = mode === 'real'

export const authApi: AuthApi = useReal ? realAuthApi : mockAuthApi
export const metaApi: MetaApi = useReal ? realMetaApi : mockMetaApi
export const historyApi: HistoryApi = useReal ? realHistoryApi : mockHistoryApi
export const liveApi: LiveApi = useReal ? realLiveApi : mockLiveApi
export const alarmApi: AlarmApi = useReal ? realAlarmApi : mockAlarmApi
```

Substituir por:

```typescript
import type { MetaApi, HistoryApi, LiveApi, AuthApi, AlarmApi, ConfigApi } from './contracts'
import { mockMetaApi } from './mock/metaApi'
import { mockHistoryApi } from './mock/historyApi'
import { mockLiveApi } from './mock/liveApi'
import { mockAuthApi } from './mock/authApi'
import { mockAlarmApi } from './mock/alarmApi'
import { mockConfigApi } from './mock/configApi'
import { realAuthApi } from './real/authApi'
import { realMetaApi } from './real/metaApi'
import { realHistoryApi } from './real/historyApi'
import { realLiveApi } from './real/liveApi'
import { realAlarmApi } from './real/alarmApi'
import { realConfigApi } from './real/configApi'

const mode = import.meta.env.VITE_API_MODE ?? 'mock'
if (mode !== 'real' && mode !== 'mock') {
  console.warn(`VITE_API_MODE=${mode} nao reconhecido; usando mock para todos os adapters`)
}

const useReal = mode === 'real'

export const authApi: AuthApi = useReal ? realAuthApi : mockAuthApi
export const metaApi: MetaApi = useReal ? realMetaApi : mockMetaApi
export const historyApi: HistoryApi = useReal ? realHistoryApi : mockHistoryApi
export const liveApi: LiveApi = useReal ? realLiveApi : mockLiveApi
export const alarmApi: AlarmApi = useReal ? realAlarmApi : mockAlarmApi
export const configApi: ConfigApi = useReal ? realConfigApi : mockConfigApi
```

Modificar `frontend/src/lib/api/index.test.ts` — arquivo atual completo:

```typescript
import { describe, it, expect } from 'vitest'
import { metaApi, historyApi, liveApi, authApi, alarmApi } from './index'

// Em teste, VITE_API_MODE e forcado para 'mock' (vite.config.ts) — este teste
// so confirma que o barril exporta todos os adapters exigidos pelo app.
describe('api barrel', () => {
  it('exporta os 5 adapters', () => {
    expect(metaApi).toBeDefined()
    expect(historyApi).toBeDefined()
    expect(liveApi).toBeDefined()
    expect(authApi).toBeDefined()
    expect(alarmApi).toBeDefined()
  })
})
```

Substituir por:

```typescript
import { describe, it, expect } from 'vitest'
import { metaApi, historyApi, liveApi, authApi, alarmApi, configApi } from './index'

// Em teste, VITE_API_MODE e forcado para 'mock' (vite.config.ts) — este teste
// so confirma que o barril exporta todos os adapters exigidos pelo app.
describe('api barrel', () => {
  it('exporta os 6 adapters', () => {
    expect(metaApi).toBeDefined()
    expect(historyApi).toBeDefined()
    expect(liveApi).toBeDefined()
    expect(authApi).toBeDefined()
    expect(alarmApi).toBeDefined()
    expect(configApi).toBeDefined()
  })
})
```

- [ ] **Step 3: Rodar os testes novos/alterados, confirmar que passam**

Run: `cd frontend && npx vitest run src/lib/api/`
Expected: PASS em todos os arquivos, incluindo `configApi.test.ts` e `index.test.ts` atualizado.

- [ ] **Step 4: `useConfig()` em `queries.ts`**

Modificar `frontend/src/lib/queries.ts` — trocar a linha de import:

```typescript
import { metaApi, historyApi, alarmApi } from './api'
```

por:

```typescript
import { metaApi, historyApi, alarmApi, configApi } from './api'
```

e adicionar, ao final do arquivo, depois de `useAlarms`:

```typescript
export function useConfig() {
  return useQuery({ queryKey: ['config'], queryFn: () => configApi.getConfig(), staleTime: 5 * 60 * 1000 })
}
```

Modificar `frontend/src/lib/queries.test.tsx` — trocar a linha de import:

```typescript
import { useSensorMeta, useThreshold, useHistory, useSensors, useThresholds, useAlarms } from './queries'
```

por:

```typescript
import { useSensorMeta, useThreshold, useHistory, useSensors, useThresholds, useAlarms, useConfig } from './queries'
```

e adicionar, ao final do `describe('queries', ...)`, depois do teste de `useAlarms`:

```typescript
  it('useConfig carrega o intervalo do carrossel do mock', async () => {
    const { result } = renderHook(() => useConfig(), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.carousel_interval_ms).toBe(3000)
  })
```

- [ ] **Step 5: Rodar os testes, confirmar que passam**

Run: `cd frontend && npx vitest run src/lib/queries.test.tsx`
Expected: PASS (7 testes, incluindo `useConfig`).

- [ ] **Step 6: `AreaCard` recebe `carouselIntervalMs` como prop obrigatória**

Modificar `frontend/src/components/AreaCard.tsx` — arquivo atual completo:

```typescript
import { sensorDisplayState, worstAlarmState, type AreaGroup } from '../lib/aggregateStatus'
import { useSensorCarousel } from '../lib/useSensorCarousel'
import { StatusChip } from './StatusChip'
import { StatusDot } from './StatusDot'
import { statusTextColor } from './statusVisuals'
import type { LivePoint, Threshold } from '../lib/types'

const BORDER_COLOR: Record<ReturnType<typeof worstAlarmState>, string> = {
  ok: 'var(--color-line)',
  warn: 'var(--color-warn)',
  crit: 'var(--color-crit)',
  unknown: 'var(--color-line)',
}

const CAROUSEL_INTERVAL_MS = 3000

export function AreaCard({
  group,
  thresholdsByCode,
  liveByCode,
  selectedSensorCode,
  onSelectSensor,
  hadAlarmToday,
}: {
  group: AreaGroup
  thresholdsByCode: Record<string, Threshold | null | undefined>
  liveByCode: Record<string, LivePoint | undefined>
  selectedSensorCode: string | null
  onSelectSensor: (code: string) => void
  hadAlarmToday: boolean
}) {
  const states = group.sensors.map((s) =>
    sensorDisplayState(thresholdsByCode[s.sensor_code] ?? null, liveByCode[s.sensor_code]),
  )
  const aggregate = worstAlarmState(states)
  const carousel = useSensorCarousel(group.sensors.length, CAROUSEL_INTERVAL_MS)
  const activeSensor = group.sensors[carousel.activeIndex] ?? group.sensors[0]
```

Substituir o trecho de `const CAROUSEL_INTERVAL_MS = 3000` até a assinatura da função (linhas 15-36) por:

```typescript
export function AreaCard({
  group,
  thresholdsByCode,
  liveByCode,
  selectedSensorCode,
  onSelectSensor,
  hadAlarmToday,
  carouselIntervalMs,
}: {
  group: AreaGroup
  thresholdsByCode: Record<string, Threshold | null | undefined>
  liveByCode: Record<string, LivePoint | undefined>
  selectedSensorCode: string | null
  onSelectSensor: (code: string) => void
  hadAlarmToday: boolean
  carouselIntervalMs: number
}) {
  const states = group.sensors.map((s) =>
    sensorDisplayState(thresholdsByCode[s.sensor_code] ?? null, liveByCode[s.sensor_code]),
  )
  const aggregate = worstAlarmState(states)
  const carousel = useSensorCarousel(group.sensors.length, carouselIntervalMs)
  const activeSensor = group.sensors[carousel.activeIndex] ?? group.sensors[0]
```

(o restante do arquivo, a partir de `const activeState = ...`, não muda).

- [ ] **Step 7: Atualizar `AreaCard.test.tsx` — prop nova em todo render + 1 teste de wiring**

Modificar `frontend/src/components/AreaCard.test.tsx` — arquivo atual completo:

```tsx
import { render, screen, fireEvent, act } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { AreaCard } from './AreaCard'
import { statusTextColor } from './statusVisuals'
import type { AreaGroup } from '../lib/aggregateStatus'

afterEach(() => vi.useRealTimers())

const group: AreaGroup = {
  area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' },
  sensors: [
    { sensor_code: 'TEMP-EXP-01', name: 'Temp', unidade: '°C', protocolo_origem: '4-20ma', measurement_type: { code: 'temperatura', name: 'Temperatura' }, area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' } },
    { sensor_code: 'PRESS-EXP-01', name: 'Pressao', unidade: 'Pa', protocolo_origem: '4-20ma', measurement_type: { code: 'pressao_diferencial', name: 'Pressão' }, area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' } },
  ],
}
const singleGroup: AreaGroup = {
  area: { area_code: 'SALA1', name: 'Sala 1', category: 'Sala' },
  sensors: [group.sensors[0]],
}
const thresholdsByCode = {
  'TEMP-EXP-01': { sensor_id: 'TEMP-EXP-01', limite_min: 18, limite_max: 26, is_valor_padrao_regulatorio: false },
  'PRESS-EXP-01': { sensor_id: 'PRESS-EXP-01', limite_min: -15, limite_max: -2.5, is_valor_padrao_regulatorio: true },
}
const liveByCode = {
  'TEMP-EXP-01': { sensor_code: 'TEMP-EXP-01', ts: 1, value: 21, alarm_state: 'ok' as const },
  'PRESS-EXP-01': { sensor_code: 'PRESS-EXP-01', ts: 1, value: -3.6, alarm_state: 'ok' as const },
}

describe('AreaCard', () => {
  it('mostra nome da area e o sensor ativo (1o da lista) com valor mono', () => {
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    expect(screen.getByText('Expurgo')).toBeInTheDocument()
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    expect(screen.getByText(/21\.0/)).toBeInTheDocument()
  })

  it('clicar no valor do sensor ativo chama onSelectSensor com o codigo certo', () => {
    const onSelectSensor = vi.fn()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={onSelectSensor} hadAlarmToday={false} />,
    )
    fireEvent.click(screen.getByText('Temperatura'))
    expect(onSelectSensor).toHaveBeenCalledWith('TEMP-EXP-01')
  })

  it('badge "!" aparece so quando hadAlarmToday=true', () => {
    const { rerender } = render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    expect(screen.queryByLabelText('Houve não conformidade hoje')).not.toBeInTheDocument()

    rerender(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday />,
    )
    expect(screen.getByLabelText('Houve não conformidade hoje')).toBeInTheDocument()
  })

  it('area com 1 sensor nao mostra dots', () => {
    render(
      <AreaCard group={singleGroup} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
  })

  it('area com N sensores mostra 1 dot por sensor', () => {
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    expect(screen.getAllByRole('tab')).toHaveLength(2)
  })

  it('avanca automaticamente entre sensores a cada 3s', () => {
    vi.useFakeTimers()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(screen.getByText('Pressão')).toBeInTheDocument()
    expect(screen.queryByText('Temperatura')).not.toBeInTheDocument()
  })

  it('hover pausa avanco automatico; mouse leave retoma o ciclo do zero', () => {
    vi.useFakeTimers()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    const card = screen.getByTestId('area-card-EXPURGO')
    fireEvent.mouseEnter(card)
    act(() => {
      vi.advanceTimersByTime(10000)
    })
    expect(screen.getByText('Temperatura')).toBeInTheDocument()

    fireEvent.mouseLeave(card)
    act(() => {
      vi.advanceTimersByTime(2999)
    })
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByText('Pressão')).toBeInTheDocument()
  })

  it('foco por teclado pausa avanco automatico; blur retoma o ciclo do zero', () => {
    vi.useFakeTimers()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    const card = screen.getByTestId('area-card-EXPURGO')
    fireEvent.focus(card)
    act(() => {
      vi.advanceTimersByTime(10000)
    })
    expect(screen.getByText('Temperatura')).toBeInTheDocument()

    fireEvent.blur(card)
    act(() => {
      vi.advanceTimersByTime(2999)
    })
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByText('Pressão')).toBeInTheDocument()
  })

  it('clicar no dot pula pro sensor certo e reinicia o ciclo de 3s', () => {
    vi.useFakeTimers()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    const dots = screen.getAllByRole('tab')
    fireEvent.click(dots[1])
    expect(screen.getByText('Pressão')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(2999)
    })
    expect(screen.getByText('Pressão')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
  })

  it('cor do valor em destaque reflete alarm_state (crit)', () => {
    const critLive = {
      ...liveByCode,
      'TEMP-EXP-01': { sensor_code: 'TEMP-EXP-01', ts: 1, value: 30, alarm_state: 'crit' as const },
    }
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={critLive}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    const value = screen.getByText(/30\.0/)
    expect(value.style.color).toBe(statusTextColor('crit'))
  })
})
```

Substituir o arquivo inteiro por esta versão (todo `render` ganha `carouselIntervalMs={3000}`; testes de tempo continuam batendo em 3000ms; 1 teste novo no final prova que a prop realmente governa o intervalo, com um valor diferente de 3000):

```tsx
import { render, screen, fireEvent, act } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { AreaCard } from './AreaCard'
import { statusTextColor } from './statusVisuals'
import type { AreaGroup } from '../lib/aggregateStatus'

afterEach(() => vi.useRealTimers())

const group: AreaGroup = {
  area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' },
  sensors: [
    { sensor_code: 'TEMP-EXP-01', name: 'Temp', unidade: '°C', protocolo_origem: '4-20ma', measurement_type: { code: 'temperatura', name: 'Temperatura' }, area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' } },
    { sensor_code: 'PRESS-EXP-01', name: 'Pressao', unidade: 'Pa', protocolo_origem: '4-20ma', measurement_type: { code: 'pressao_diferencial', name: 'Pressão' }, area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' } },
  ],
}
const singleGroup: AreaGroup = {
  area: { area_code: 'SALA1', name: 'Sala 1', category: 'Sala' },
  sensors: [group.sensors[0]],
}
const thresholdsByCode = {
  'TEMP-EXP-01': { sensor_id: 'TEMP-EXP-01', limite_min: 18, limite_max: 26, is_valor_padrao_regulatorio: false },
  'PRESS-EXP-01': { sensor_id: 'PRESS-EXP-01', limite_min: -15, limite_max: -2.5, is_valor_padrao_regulatorio: true },
}
const liveByCode = {
  'TEMP-EXP-01': { sensor_code: 'TEMP-EXP-01', ts: 1, value: 21, alarm_state: 'ok' as const },
  'PRESS-EXP-01': { sensor_code: 'PRESS-EXP-01', ts: 1, value: -3.6, alarm_state: 'ok' as const },
}

describe('AreaCard', () => {
  it('mostra nome da area e o sensor ativo (1o da lista) com valor mono', () => {
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
    )
    expect(screen.getByText('Expurgo')).toBeInTheDocument()
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    expect(screen.getByText(/21\.0/)).toBeInTheDocument()
  })

  it('clicar no valor do sensor ativo chama onSelectSensor com o codigo certo', () => {
    const onSelectSensor = vi.fn()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={onSelectSensor} hadAlarmToday={false} carouselIntervalMs={3000} />,
    )
    fireEvent.click(screen.getByText('Temperatura'))
    expect(onSelectSensor).toHaveBeenCalledWith('TEMP-EXP-01')
  })

  it('badge "!" aparece so quando hadAlarmToday=true', () => {
    const { rerender } = render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
    )
    expect(screen.queryByLabelText('Houve não conformidade hoje')).not.toBeInTheDocument()

    rerender(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday carouselIntervalMs={3000} />,
    )
    expect(screen.getByLabelText('Houve não conformidade hoje')).toBeInTheDocument()
  })

  it('area com 1 sensor nao mostra dots', () => {
    render(
      <AreaCard group={singleGroup} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
    )
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
  })

  it('area com N sensores mostra 1 dot por sensor', () => {
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
    )
    expect(screen.getAllByRole('tab')).toHaveLength(2)
  })

  it('avanca automaticamente entre sensores a cada 3s', () => {
    vi.useFakeTimers()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
    )
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(screen.getByText('Pressão')).toBeInTheDocument()
    expect(screen.queryByText('Temperatura')).not.toBeInTheDocument()
  })

  it('hover pausa avanco automatico; mouse leave retoma o ciclo do zero', () => {
    vi.useFakeTimers()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
    )
    const card = screen.getByTestId('area-card-EXPURGO')
    fireEvent.mouseEnter(card)
    act(() => {
      vi.advanceTimersByTime(10000)
    })
    expect(screen.getByText('Temperatura')).toBeInTheDocument()

    fireEvent.mouseLeave(card)
    act(() => {
      vi.advanceTimersByTime(2999)
    })
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByText('Pressão')).toBeInTheDocument()
  })

  it('foco por teclado pausa avanco automatico; blur retoma o ciclo do zero', () => {
    vi.useFakeTimers()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
    )
    const card = screen.getByTestId('area-card-EXPURGO')
    fireEvent.focus(card)
    act(() => {
      vi.advanceTimersByTime(10000)
    })
    expect(screen.getByText('Temperatura')).toBeInTheDocument()

    fireEvent.blur(card)
    act(() => {
      vi.advanceTimersByTime(2999)
    })
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByText('Pressão')).toBeInTheDocument()
  })

  it('clicar no dot pula pro sensor certo e reinicia o ciclo de 3s', () => {
    vi.useFakeTimers()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
    )
    const dots = screen.getAllByRole('tab')
    fireEvent.click(dots[1])
    expect(screen.getByText('Pressão')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(2999)
    })
    expect(screen.getByText('Pressão')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
  })

  it('cor do valor em destaque reflete alarm_state (crit)', () => {
    const critLive = {
      ...liveByCode,
      'TEMP-EXP-01': { sensor_code: 'TEMP-EXP-01', ts: 1, value: 30, alarm_state: 'crit' as const },
    }
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={critLive}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
    )
    const value = screen.getByText(/30\.0/)
    expect(value.style.color).toBe(statusTextColor('crit'))
  })

  it('carouselIntervalMs vindo por prop governa o intervalo (nao mais fixo em 3000)', () => {
    vi.useFakeTimers()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={100} />,
    )
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(99)
    })
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByText('Pressão')).toBeInTheDocument()
  })
})
```

- [ ] **Step 8: Rodar os testes do componente, confirmar que passam**

Run: `cd frontend && npx vitest run src/components/AreaCard.test.tsx`
Expected: PASS (10/10, incluindo o teste novo de wiring da prop).

- [ ] **Step 9: `DashboardPage` busca a config e repassa pro `AreaCard`**

Modificar `frontend/src/pages/DashboardPage.tsx` — trocar a linha de import (linha 4):

```typescript
import { useSensors, useThresholds, useHistory, useAlarms } from '../lib/queries'
```

por:

```typescript
import { useSensors, useThresholds, useHistory, useAlarms, useConfig } from '../lib/queries'
```

Logo após `const sensorsQuery = useSensors()` (linha 33), adicionar:

```typescript
  const configQuery = useConfig()
  const carouselIntervalMs = configQuery.data?.carousel_interval_ms ?? 3000
```

No JSX do `AreaCard` (linhas 101-109), adicionar a prop nova:

```tsx
                {groups.map((g) => (
                  <AreaCard
                    key={g.area.area_code}
                    group={g}
                    thresholdsByCode={thresholdsByCode}
                    liveByCode={liveByCode}
                    selectedSensorCode={selectedCode}
                    onSelectSensor={selectSensor}
                    hadAlarmToday={alarms.some((a) => a.area_code === g.area.area_code && isToday(a.timestamp_deteccao))}
                    carouselIntervalMs={carouselIntervalMs}
                  />
                ))}
```

- [ ] **Step 10: Rodar a suite inteira do frontend + typecheck, confirmar que nada quebrou**

Run: `cd frontend && npx vitest run && npx tsc -b`
Expected: PASS em todos os arquivos (a única falha esperada, pré-existente e não relacionada, é `src/lib/demoMode.test.ts` por causa de um `.env.local` local com `VITE_DEMO_MODE=true` — confirmar que é a única). `tsc -b` sem erros novos (o único erro pré-existente conhecido é em `chartOption.ts:71`, ECharts `markArea`, não relacionado a esta feature).

- [ ] **Step 11: Commit**

```bash
git add frontend/src/lib/types.ts \
        frontend/src/lib/api/contracts.ts \
        frontend/src/lib/api/mock/configApi.ts \
        frontend/src/lib/api/real/configApi.ts \
        frontend/src/lib/api/real/configApi.test.ts \
        frontend/src/lib/api/index.ts \
        frontend/src/lib/api/index.test.ts \
        frontend/src/lib/queries.ts \
        frontend/src/lib/queries.test.tsx \
        frontend/src/pages/DashboardPage.tsx \
        frontend/src/components/AreaCard.tsx \
        frontend/src/components/AreaCard.test.tsx
git commit -m "feat(frontend): intervalo do carrossel vem de /config (ConfigApi + useConfig)"
```
