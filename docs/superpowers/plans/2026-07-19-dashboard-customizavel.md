# Dashboard Customizável por Site — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que um admin monte o layout do dashboard por site numa grade livre (drag+resize) de widgets, persistido como blob JSON no Odoo; operadores apenas visualizam.

**Architecture:** Layout = 1 blob JSON armazenado opaco no model Odoo `sensor_monitor.dashboard.config` (único por site). Frontend é dono do schema (valida com zod). `GET /config` devolve o blob; `PUT /config/layout` (admin-only) grava. React renderiza via `react-grid-layout`, cada widget resolve seu binding (area/sensor) para dados através dos hooks React Query existentes.

**Tech Stack:** Odoo 16 (Python/XML-RPC), FastAPI + PyJWT, React 19 + Vite 8 + TypeScript, @tanstack/react-query v5, **zod (novo)**, **react-grid-layout (novo)**, Vitest + Testing Library (unit/component), chrome-devtools-mcp / agent-web (verificação real-browser).

## Global Constraints

- **Idioma:** identificadores/código em inglês; comentários e strings de UI em português (padrão do repo).
- **Backend em português:** nomes de função Python em português quando o padrão local for (ex: `obter_config`, `exigir_admin`), seguindo `api/config.py` e `api/auth.py`.
- **Persistência:** layout é **blob opaco** no Odoo. Odoo/API não validam a forma interna (só sanity-check leve). Validação de forma detalhada é do frontend (zod).
- **Um site por instância da API:** `SITE_CODE` vem de env (`SENTINELA_SITE_CODE`, default `SITE-DEMO-01`). Endpoints operam sobre esse site — sem parâmetro de site.
- **Backend tests = integração real:** os testes de API/Odoo rodam contra Odoo vivo + API viva (login `admin/admin`), criam/limpam registros com `try/finally`. NÃO há mock de Odoo. Padrão em `api/tests/test_config.py`.
- **Frontend tests:** Vitest, colocados como `*.test.ts(x)` ao lado do source. Config em `frontend/vite.config.ts` (campo `test`, `environment: jsdom`, `VITE_API_MODE: 'mock'`). Import explícito de `vitest`. Mock de rede via `vi.stubGlobal('fetch', ...)`.
- **Query keys:** tuplas de string planas (`['config']`, `['sensors']`, `['threshold', code]`).
- **TDD sempre:** teste falhando → implementação mínima → verde → commit. Commits frequentes.
- **Comandos:** frontend a partir de `frontend/` (`npm test`, `npm run build`). Backend a partir da raiz (`pytest api/tests/... -v`). Odoo tests: rodar suíte do módulo `afr_sentinela_sensor_monitor` (usar `--test-tags` do módulo, nunca suíte inteira do base).

## Riscos conhecidos (ler antes de começar)

1. **`react-grid-layout` peer dep vs React 19:** `react-grid-layout` declara peer `react@">=16 <19"`. Instalar com `npm install react-grid-layout @types/react-grid-layout` pode dar `ERESOLVE`. Se ocorrer, instalar com `--legacy-peer-deps`. Verificar drag/resize real no browser (Task 15) — se quebrar em runtime com React 19, fallback: usar `react-grid-layout`'s `WidthProvider`/`Responsive` só em modo leitura+edição desktop (não usamos features exóticas). Registrar o comando usado no commit.
2. **JWT sem claim de papel hoje:** Task 2 adiciona. Mudança no payload de login — confirmar que testes de login existentes não fixam o shape exato do payload (eles checam só `access_token`).
3. **Odoo `groups_id` / grupo admin:** Task 2 lê grupos do usuário. Definir o critério de "admin": usar o grupo `base.group_system` (Administração/Settings) OU um grupo dedicado do módulo. Este plano usa **`base.group_system`** via `res.users.has_group('base.group_system')` (mais simples, sem migração de dados). Ajustável.

---

### Task 1: Odoo — campos `layout_json` e `layout_version`

**Files:**
- Modify: `addons/afr_sentinela_sensor_monitor/models/dashboard_config.py`
- Test: `addons/afr_sentinela_sensor_monitor/tests/test_dashboard_config.py`

**Interfaces:**
- Produces: model `sensor_monitor.dashboard.config` com campos novos `layout_json` (Text, nullable) e `layout_version` (Integer, default 1). Constraint: se `layout_json` preenchido, deve ser JSON parseável.

- [ ] **Step 1: Escrever teste falhando** (append em `test_dashboard_config.py`)

Localizar a classe de teste existente (TransactionCase) e adicionar métodos. Se o arquivo usar o padrão Odoo `TransactionCase`, seguir; senão espelhar o estilo existente. Código a adicionar:

```python
    def test_layout_json_persiste(self):
        site = self._site()
        config = self.env['sensor_monitor.dashboard.config'].create({
            'site_id': site.id,
            'layout_json': '{"version": 1, "grid": {"cols": 12, "rowHeight": 40, "margin": [8, 8]}, "widgets": []}',
            'layout_version': 1,
        })
        self.assertEqual(config.layout_version, 1)
        self.assertIn('"version": 1', config.layout_json)

    def test_layout_json_invalido_rejeitado(self):
        site = self._site()
        with self.assertRaises(ValidationError):
            self.env['sensor_monitor.dashboard.config'].create({
                'site_id': site.id,
                'layout_json': 'isso nao e json',
            })

    def test_layout_version_default_um(self):
        site = self._site()
        config = self.env['sensor_monitor.dashboard.config'].create({'site_id': site.id})
        self.assertEqual(config.layout_version, 1)
```

Se ainda não houver um helper `_site()` na classe de teste, adicionar:

```python
    def _site(self):
        site = self.env['sensor_monitor.site'].search([('site_code', '=', 'SITE-TEST-CFG')], limit=1)
        if not site:
            partner = self.env['res.partner'].create({'name': 'Partner teste config'})
            site = self.env['sensor_monitor.site'].create({
                'name': 'Site teste config',
                'partner_id': partner.id,
                'site_code': 'SITE-TEST-CFG',
                'vertical': 'cme_hospitalar',
            })
        return site
```

Garantir imports no topo do arquivo de teste: `from odoo.exceptions import ValidationError`.

- [ ] **Step 2: Rodar teste, verificar que falha**

Run: `docker compose exec -T odoo odoo -d sentinela --test-enable --test-tags /afr_sentinela_sensor_monitor --stop-after-init -i afr_sentinela_sensor_monitor 2>&1 | grep -iE "test_layout|FAIL|ERROR"`

(Ajustar o comando ao runner de testes Odoo do projeto — ver como os testes atuais são invocados; se houver script/Makefile, usar. O ponto é rodar SÓ as tags do módulo.)
Expected: FAIL — campo `layout_json`/`layout_version` não existe.

- [ ] **Step 3: Implementar campos + constraint** (`dashboard_config.py`)

```python
import json

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DashboardConfig(models.Model):
    _name = 'sensor_monitor.dashboard.config'
    _description = 'Configuração do Dashboard'

    site_id = fields.Many2one('sensor_monitor.site', required=True, ondelete='cascade')
    carousel_interval_ms = fields.Integer(
        default=3000, required=True, string='Intervalo do carrossel (ms)',
    )
    layout_json = fields.Text(string='Layout do dashboard (JSON)')
    layout_version = fields.Integer(string='Versão do schema de layout', default=1)

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

    @api.constrains('layout_json')
    def _check_layout_json_parseavel(self):
        for config in self:
            if not config.layout_json:
                continue
            try:
                json.loads(config.layout_json)
            except (ValueError, TypeError):
                raise ValidationError('layout_json deve ser um JSON válido.')
```

- [ ] **Step 4: Rodar teste, verificar verde**

Run: mesmo comando do Step 2.
Expected: PASS para `test_layout_json_persiste`, `test_layout_json_invalido_rejeitado`, `test_layout_version_default_um`.

- [ ] **Step 5: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor/models/dashboard_config.py addons/afr_sentinela_sensor_monitor/tests/test_dashboard_config.py
git commit -m "feat(odoo): dashboard.config ganha layout_json + layout_version (blob opaco)"
```

---

### Task 2: JWT — claim `is_admin` + dependency `exigir_admin`

**Files:**
- Modify: `api/auth.py`
- Test: `api/tests/test_auth_admin.py` (Create)

**Interfaces:**
- Consumes: `verificar_token` (existente, devolve claims dict), `get_cliente_servico`, `odoo_cliente.executar`.
- Produces:
  - Login inclui claim `is_admin: bool` no JWT (True se o usuário Odoo tem `base.group_system`).
  - `exigir_admin(claims=Depends(verificar_token)) -> dict` — 403 se `claims.get('is_admin')` falso; devolve claims se admin.

- [ ] **Step 1: Escrever teste falhando** (`api/tests/test_auth_admin.py`)

```python
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def _login(usuario, senha):
    return client.post('/auth/login', json={'usuario': usuario, 'senha': senha})


def test_login_admin_tem_claim_is_admin_true():
    import jwt as _jwt
    from api.auth import SECRET, ALGORITHM

    resp = _login('admin', 'admin')
    assert resp.status_code == 200
    token = resp.json()['access_token']
    claims = _jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    assert claims.get('is_admin') is True
```

- [ ] **Step 2: Rodar teste, verificar que falha**

Run: `pytest api/tests/test_auth_admin.py -v`
Expected: FAIL — claim `is_admin` ausente (KeyError/None).

- [ ] **Step 3: Implementar claim + `exigir_admin`** (`api/auth.py`)

No `login`, após obter `cliente_usuario`, calcular admin com o cliente do próprio usuário e adicionar ao payload:

```python
    is_admin = bool(
        odoo_cliente.executar(
            cliente_usuario, 'res.users', 'has_group', 'base.group_system',
        )
    )

    payload = {
        'sub': str(cliente_usuario.uid),
        'partner_id': partner_id,
        'is_admin': is_admin,
        'exp': int(time.time()) + EXPIRACAO_SEGUNDOS,
    }
```

Nota: `has_group` no XML-RPC roda no contexto do uid do `cliente_usuario` (o próprio usuário logado), então avalia o grupo dele. Se `has_group` via `execute_kw` não aceitar essa assinatura no ambiente, alternativa equivalente:

```python
    grupo = odoo_cliente.executar(
        cliente_servico, 'res.groups', 'search',
        [('full_name', '=', 'Administration / Settings')], limit=1,
    )
    is_admin = False
    if grupo:
        users = odoo_cliente.executar(
            cliente_servico, 'res.users', 'search_read',
            [('id', '=', cliente_usuario.uid), ('groups_id', 'in', grupo)], fields=['id'],
        )
        is_admin = bool(users)
```

Usar a primeira forma; cair na segunda só se a primeira falhar em runtime (verificar rodando o teste).

Adicionar a dependency ao final do arquivo:

```python
def exigir_admin(claims: dict = Depends(verificar_token)):
    if not claims.get('is_admin'):
        raise HTTPException(status_code=403, detail='requer privilégio de administrador')
    return claims
```

- [ ] **Step 4: Rodar teste, verificar verde**

Run: `pytest api/tests/test_auth_admin.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/auth.py api/tests/test_auth_admin.py
git commit -m "feat(api): JWT carrega is_admin + dependency exigir_admin (403 nao-admin)"
```

---

### Task 3: API — `GET /config` com layout + `PUT /config/layout`

**Files:**
- Modify: `api/config.py`
- Test: `api/tests/test_config.py`

**Interfaces:**
- Consumes: `exigir_admin` (Task 2), `verificar_token`, `get_cliente_servico`, `SITE_CODE`, `odoo_cliente.executar`.
- Produces:
  - `GET /config` retorna `{ carousel_interval_ms, layout }` onde `layout` é o objeto parseado de `layout_json` ou `None`.
  - `PUT /config/layout` (Body `{ layout: object }`, admin-only): upsert do registro do site; sanity-check (`layout` é dict, `version` int, `widgets` lista); grava `layout_json`/`layout_version`; retorna `{ layout }`.

- [ ] **Step 1: Escrever teste falhando** (append em `api/tests/test_config.py`)

```python
def test_config_retorna_layout_quando_salvo():
    cliente = get_cliente_servico()
    site_id = _site_id(cliente)
    layout = {'version': 1, 'grid': {'cols': 12, 'rowHeight': 40, 'margin': [8, 8]}, 'widgets': []}
    import json as _json
    config_id = odoo_cliente.executar(
        cliente, 'sensor_monitor.dashboard.config', 'create',
        {'site_id': site_id, 'layout_json': _json.dumps(layout)},
    )
    try:
        resposta = client.get('/config', headers=_headers())
        assert resposta.status_code == 200
        assert resposta.json()['layout'] == layout
    finally:
        odoo_cliente.executar(cliente, 'sensor_monitor.dashboard.config', 'unlink', [config_id])


def test_config_layout_none_quando_ausente():
    cliente = get_cliente_servico()
    site_id = _site_id(cliente)
    existentes = odoo_cliente.executar(
        cliente, 'sensor_monitor.dashboard.config', 'search',
        [('site_id', '=', site_id)],
    )
    if existentes:
        odoo_cliente.executar(cliente, 'sensor_monitor.dashboard.config', 'unlink', existentes)
    resposta = client.get('/config', headers=_headers())
    assert resposta.status_code == 200
    assert resposta.json()['layout'] is None


def test_put_layout_admin_faz_upsert():
    cliente = get_cliente_servico()
    site_id = _site_id(cliente)
    existentes = odoo_cliente.executar(
        cliente, 'sensor_monitor.dashboard.config', 'search',
        [('site_id', '=', site_id)],
    )
    if existentes:
        odoo_cliente.executar(cliente, 'sensor_monitor.dashboard.config', 'unlink', existentes)
    layout = {'version': 1, 'grid': {'cols': 12, 'rowHeight': 40, 'margin': [8, 8]},
              'widgets': [{'id': 'w1', 'type': 'kpi', 'layout': {'x': 0, 'y': 0, 'w': 2, 'h': 2},
                           'binding': {'sensorCode': 'PRESS-EXP-01'}, 'options': {}}]}
    try:
        resposta = client.put('/config/layout', json={'layout': layout}, headers=_headers())
        assert resposta.status_code == 200
        assert resposta.json()['layout'] == layout
        get_resp = client.get('/config', headers=_headers())
        assert get_resp.json()['layout'] == layout
    finally:
        atuais = odoo_cliente.executar(
            cliente, 'sensor_monitor.dashboard.config', 'search',
            [('site_id', '=', site_id)],
        )
        if atuais:
            odoo_cliente.executar(cliente, 'sensor_monitor.dashboard.config', 'unlink', atuais)


def test_put_layout_sem_token_401():
    resposta = client.put('/config/layout', json={'layout': {'version': 1, 'widgets': []}})
    assert resposta.status_code == 401


def test_put_layout_body_malformado_422_ou_400():
    resposta = client.put('/config/layout', json={'layout': {'version': 1}}, headers=_headers())
    assert resposta.status_code in (400, 422)
```

(Nota: os testes de admin assumem `admin/admin` = admin, verdadeiro pós-Task 2. Um teste de 403 para não-admin exigiria um usuário não-admin no Odoo; se não existir fixture, deixar coberto pelo teste unitário de `exigir_admin` no Task 2 e anotar no commit. NÃO inventar usuário.)

- [ ] **Step 2: Rodar teste, verificar que falha**

Run: `pytest api/tests/test_config.py -v -k "layout"`
Expected: FAIL — `PUT /config/layout` não existe (405/404); `GET` não traz `layout`.

- [ ] **Step 3: Implementar** (`api/config.py`)

```python
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ingestao import odoo_cliente

from .auth import exigir_admin, verificar_token
from .odoo import SITE_CODE, get_cliente_servico

router = APIRouter()

_DEFAULT_CAROUSEL_INTERVAL_MS = 3000


class LayoutBody(BaseModel):
    layout: dict


def _site_id_do_code(cliente):
    sites = odoo_cliente.executar(
        cliente, 'sensor_monitor.site', 'search_read',
        [('site_code', '=', SITE_CODE)], fields=['id'],
    )
    return sites[0]['id'] if sites else None


def obter_config(cliente):
    site_id = _site_id_do_code(cliente)
    if site_id is None:
        return {'carousel_interval_ms': _DEFAULT_CAROUSEL_INTERVAL_MS, 'layout': None}

    configs = odoo_cliente.executar(
        cliente, 'sensor_monitor.dashboard.config', 'search_read',
        [('site_id', '=', site_id)], fields=['carousel_interval_ms', 'layout_json'],
    )
    if not configs:
        return {'carousel_interval_ms': _DEFAULT_CAROUSEL_INTERVAL_MS, 'layout': None}

    cfg = configs[0]
    layout = json.loads(cfg['layout_json']) if cfg.get('layout_json') else None
    return {'carousel_interval_ms': cfg['carousel_interval_ms'], 'layout': layout}


@router.get('/config')
def get_config(cliente=Depends(get_cliente_servico), _claims=Depends(verificar_token)):
    return obter_config(cliente)


@router.put('/config/layout')
def put_layout(body: LayoutBody, cliente=Depends(get_cliente_servico), _claims=Depends(exigir_admin)):
    layout = body.layout
    if not isinstance(layout, dict) or not isinstance(layout.get('version'), int) \
            or not isinstance(layout.get('widgets'), list):
        raise HTTPException(status_code=400, detail='layout inválido: requer version(int) e widgets(list)')

    site_id = _site_id_do_code(cliente)
    if site_id is None:
        raise HTTPException(status_code=404, detail=f'site {SITE_CODE} não encontrado')

    valores = {'layout_json': json.dumps(layout), 'layout_version': layout['version']}
    existentes = odoo_cliente.executar(
        cliente, 'sensor_monitor.dashboard.config', 'search',
        [('site_id', '=', site_id)],
    )
    if existentes:
        odoo_cliente.executar(cliente, 'sensor_monitor.dashboard.config', 'write', existentes, valores)
    else:
        odoo_cliente.executar(
            cliente, 'sensor_monitor.dashboard.config', 'create', {'site_id': site_id, **valores},
        )
    return {'layout': layout}
```

Nota: `get_cliente_servico` usado como `Depends` — hoje `obter_config` recebe `cliente` já assim (o `Depends(get_cliente_servico)` chama a função `@lru_cache`). Manter idêntico ao padrão existente do arquivo.

- [ ] **Step 4: Rodar teste, verificar verde**

Run: `pytest api/tests/test_config.py -v`
Expected: PASS (todos, incluindo os pré-existentes de carousel).

- [ ] **Step 5: Commit**

```bash
git add api/config.py api/tests/test_config.py
git commit -m "feat(api): GET /config traz layout + PUT /config/layout (admin, upsert, sanity-check)"
```

---

### Task 4: Frontend — tipos de layout + schema zod (`parseLayout`, `migrate`)

**Files:**
- Create: `frontend/src/lib/layout/schema.ts`
- Create: `frontend/src/lib/layout/schema.test.ts`
- Modify: `frontend/src/lib/types.ts` (estender `DashboardConfig`)
- Modify: `frontend/package.json` (add `zod`)

**Interfaces:**
- Produces:
  - Tipos `WidgetType`, `WidgetInstance`, `DashboardLayout` (ver §3 do spec).
  - `parseLayout(raw: unknown): DashboardLayout | null` — devolve layout válido ou `null` (nunca lança).
  - `migrate(raw: unknown): unknown` — normaliza por `version` (no-op v1).
  - `DashboardConfig` agora tem `layout: DashboardLayout | null`.

- [ ] **Step 1: Adicionar zod**

Run (em `frontend/`): `npm install zod`
Expected: `zod` em `dependencies`.

- [ ] **Step 2: Escrever teste falhando** (`frontend/src/lib/layout/schema.test.ts`)

```ts
import { describe, it, expect } from 'vitest'
import { parseLayout, migrate } from './schema'

const validLayout = {
  version: 1,
  grid: { cols: 12, rowHeight: 40, margin: [8, 8] },
  widgets: [
    { id: 'w1', type: 'kpi', layout: { x: 0, y: 0, w: 2, h: 2 }, binding: { sensorCode: 'S1' }, options: {} },
  ],
}

describe('parseLayout', () => {
  it('aceita layout válido', () => {
    expect(parseLayout(validLayout)).toEqual(validLayout)
  })
  it('devolve null para não-objeto', () => {
    expect(parseLayout('nope')).toBeNull()
    expect(parseLayout(null)).toBeNull()
  })
  it('devolve null quando widget tem type desconhecido', () => {
    const bad = { ...validLayout, widgets: [{ ...validLayout.widgets[0], type: 'foo' }] }
    expect(parseLayout(bad)).toBeNull()
  })
  it('devolve null quando falta layout.x', () => {
    const bad = { ...validLayout, widgets: [{ ...validLayout.widgets[0], layout: { y: 0, w: 2, h: 2 } }] }
    expect(parseLayout(bad)).toBeNull()
  })
})

describe('migrate', () => {
  it('é no-op para version 1', () => {
    expect(migrate(validLayout)).toEqual(validLayout)
  })
})
```

- [ ] **Step 3: Rodar teste, verificar que falha**

Run: `npm test -- schema`
Expected: FAIL — módulo não existe.

- [ ] **Step 4: Implementar** (`frontend/src/lib/layout/schema.ts`)

```ts
import { z } from 'zod'

export const WIDGET_TYPES = ['area', 'timeseries', 'alarms', 'kpi'] as const
export type WidgetType = (typeof WIDGET_TYPES)[number]

const widgetLayoutSchema = z.object({
  x: z.number(),
  y: z.number(),
  w: z.number(),
  h: z.number(),
  minW: z.number().optional(),
  minH: z.number().optional(),
})

const widgetInstanceSchema = z.object({
  id: z.string(),
  type: z.enum(WIDGET_TYPES),
  layout: widgetLayoutSchema,
  binding: z.object({
    areaCode: z.string().optional(),
    sensorCode: z.string().optional(),
  }),
  options: z.record(z.unknown()).optional().default({}),
})

const dashboardLayoutSchema = z.object({
  version: z.literal(1),
  grid: z.object({
    cols: z.number(),
    rowHeight: z.number(),
    margin: z.tuple([z.number(), z.number()]),
  }),
  widgets: z.array(widgetInstanceSchema),
})

export type WidgetInstance = z.infer<typeof widgetInstanceSchema>
export type DashboardLayout = z.infer<typeof dashboardLayoutSchema>

// Ponto de extensão para versões futuras do schema. Hoje (v1) é no-op.
export function migrate(raw: unknown): unknown {
  return raw
}

export function parseLayout(raw: unknown): DashboardLayout | null {
  const result = dashboardLayoutSchema.safeParse(migrate(raw))
  return result.success ? result.data : null
}
```

- [ ] **Step 5: Estender `DashboardConfig`** (`frontend/src/lib/types.ts`)

Substituir a definição atual:

```ts
import type { DashboardLayout } from './layout/schema'

export type DashboardConfig = {
  carousel_interval_ms: number
  layout?: DashboardLayout | null
}
```

`layout` é **opcional** de propósito: assim o mock atual (`{ carousel_interval_ms: 4000 }`) typecheck limpo até o Task 6 preenchê-lo, e o checkpoint verde deste task não depende do Task 6. `parseLayout(configQuery.data?.layout)` lida com `undefined` (safeParse falha → defaultLayout).

(Se import circular incomodar — `types.ts` importando de `layout/schema.ts` que não importa `types.ts` — está ok, é acíclico.)

- [ ] **Step 6: Rodar teste + typecheck**

Run: `npm test -- schema && npx tsc -b --noEmit`
Expected: PASS nos testes **e tsc limpo** (campo `layout` é opcional — mock atual continua válido). Se tsc acusar erro, o campo não foi feito opcional — corrigir antes de commitar (checkpoint deve ser verde).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/layout/schema.ts frontend/src/lib/layout/schema.test.ts frontend/src/lib/types.ts frontend/package.json frontend/package-lock.json
git commit -m "feat(frontend): schema zod de DashboardLayout + parseLayout/migrate; DashboardConfig ganha layout"
```

---

### Task 5: Frontend — gerador `defaultLayout`

**Files:**
- Create: `frontend/src/lib/layout/defaultLayout.ts`
- Create: `frontend/src/lib/layout/defaultLayout.test.ts`

**Interfaces:**
- Consumes: `DashboardLayout`, `WidgetInstance` (Task 4); `AreaGroup` de `../aggregateStatus`.
- Produces: `defaultLayout(groups: AreaGroup[]): DashboardLayout` — determinístico: 1 widget `area` por grupo + 1 widget `alarms` (scope site). IDs derivados do area_code (estáveis).

- [ ] **Step 1: Escrever teste falhando** (`defaultLayout.test.ts`)

```ts
import { describe, it, expect } from 'vitest'
import { defaultLayout } from './defaultLayout'
import type { AreaGroup } from '../aggregateStatus'

function group(areaCode: string): AreaGroup {
  return { area: { area_code: areaCode, name: areaCode, category: 'cme' }, sensors: [] } as AreaGroup
}

describe('defaultLayout', () => {
  it('gera 1 widget area por grupo + 1 alarms', () => {
    const layout = defaultLayout([group('A'), group('B')])
    const areas = layout.widgets.filter((w) => w.type === 'area')
    const alarms = layout.widgets.filter((w) => w.type === 'alarms')
    expect(areas).toHaveLength(2)
    expect(alarms).toHaveLength(1)
    expect(areas[0].binding.areaCode).toBe('A')
  })
  it('é determinístico', () => {
    expect(defaultLayout([group('A')])).toEqual(defaultLayout([group('A')]))
  })
  it('IDs são estáveis por area_code', () => {
    const l = defaultLayout([group('EXPURGO')])
    expect(l.widgets.find((w) => w.type === 'area')!.id).toContain('EXPURGO')
  })
})
```

- [ ] **Step 2: Rodar teste, verificar que falha**

Run: `npm test -- defaultLayout`
Expected: FAIL.

- [ ] **Step 3: Implementar** (`defaultLayout.ts`)

```ts
import type { AreaGroup } from '../aggregateStatus'
import type { DashboardLayout, WidgetInstance } from './schema'

const COLS = 12
const AREA_W = 3
const AREA_H = 3

// Layout inicial quando nenhum foi salvo: reproduz o dashboard atual
// (um card por área numa grade + painel de alarmes à direita).
export function defaultLayout(groups: AreaGroup[]): DashboardLayout {
  const perRow = Math.max(1, Math.floor((COLS - AREA_W) / AREA_W)) // deixa espaço p/ alarms
  const widgets: WidgetInstance[] = groups.map((g, i) => ({
    id: `area-${g.area.area_code}`,
    type: 'area',
    layout: {
      x: (i % perRow) * AREA_W,
      y: Math.floor(i / perRow) * AREA_H,
      w: AREA_W,
      h: AREA_H,
    },
    binding: { areaCode: g.area.area_code },
    options: {},
  }))

  widgets.push({
    id: 'alarms-site',
    type: 'alarms',
    layout: { x: COLS - AREA_W, y: 0, w: AREA_W, h: AREA_H * 2 },
    binding: {},
    options: { scope: 'site' },
  })

  return {
    version: 1,
    grid: { cols: COLS, rowHeight: 40, margin: [8, 8] },
    widgets,
  }
}
```

- [ ] **Step 4: Rodar teste, verificar verde**

Run: `npm test -- defaultLayout`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/layout/defaultLayout.ts frontend/src/lib/layout/defaultLayout.test.ts
git commit -m "feat(frontend): defaultLayout determinístico (area por grupo + alarms)"
```

---

### Task 6: Frontend — ConfigApi estendido + helper POST/PUT + mock/real `saveLayout`

**Files:**
- Modify: `frontend/src/lib/api/contracts.ts`
- Modify: `frontend/src/lib/api/real/http.ts` (add write helper)
- Modify: `frontend/src/lib/api/mock/configApi.ts`
- Modify: `frontend/src/lib/api/real/configApi.ts`
- Test: `frontend/src/lib/api/mock/configApi.test.ts` (Create), `frontend/src/lib/api/real/configApi.test.ts` (Modify)

**Interfaces:**
- Consumes: `DashboardConfig` (com `layout`), `DashboardLayout` (Task 4).
- Produces:
  - `ConfigApi = { getConfig(): Promise<DashboardConfig>; saveLayout(layout: DashboardLayout): Promise<{ layout: DashboardLayout }> }`.
  - `authFetchJsonWrite<T>(path, method, body): Promise<T>` em `real/http.ts`.
  - mock `saveLayout` guarda em memória de módulo; mock `getConfig` reflete o salvo (round-trip provável).

- [ ] **Step 1: Escrever testes falhando**

`mock/configApi.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import { mockConfigApi } from './configApi'
import type { DashboardLayout } from '../../layout/schema'

const layout: DashboardLayout = {
  version: 1, grid: { cols: 12, rowHeight: 40, margin: [8, 8] },
  widgets: [{ id: 'w1', type: 'kpi', layout: { x: 0, y: 0, w: 2, h: 2 }, binding: { sensorCode: 'S1' }, options: {} }],
}

describe('mockConfigApi', () => {
  it('getConfig traz carousel_interval_ms e layout', async () => {
    const cfg = await mockConfigApi.getConfig()
    expect(typeof cfg.carousel_interval_ms).toBe('number')
    expect('layout' in cfg).toBe(true)
  })
  it('saveLayout persiste em memória (round-trip via getConfig)', async () => {
    await mockConfigApi.saveLayout(layout)
    const cfg = await mockConfigApi.getConfig()
    expect(cfg.layout).toEqual(layout)
  })
})
```

`real/configApi.test.ts` (adicionar caso):
```ts
import { describe, it, expect, vi, afterEach } from 'vitest'
import { realConfigApi } from './configApi'
import type { DashboardLayout } from '../../layout/schema'

afterEach(() => vi.unstubAllGlobals())

describe('realConfigApi', () => {
  it('getConfig chama GET /config e devolve o JSON', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ carousel_interval_ms: 7000, layout: null }) })
    vi.stubGlobal('fetch', mockFetch)
    const result = await realConfigApi.getConfig()
    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/config'), expect.anything())
    expect(result).toEqual({ carousel_interval_ms: 7000, layout: null })
  })

  it('saveLayout faz PUT /config/layout com body { layout }', async () => {
    const layout: DashboardLayout = {
      version: 1, grid: { cols: 12, rowHeight: 40, margin: [8, 8] }, widgets: [],
    }
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ layout }) })
    vi.stubGlobal('fetch', mockFetch)
    const result = await realConfigApi.saveLayout(layout)
    const [url, init] = mockFetch.mock.calls[0]
    expect(url).toContain('/config/layout')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body)).toEqual({ layout })
    expect(result).toEqual({ layout })
  })
})
```

- [ ] **Step 2: Rodar testes, verificar que falham**

Run: `npm test -- configApi`
Expected: FAIL — `saveLayout` não existe.

- [ ] **Step 3: Estender contrato** (`contracts.ts`)

```ts
import type { DashboardLayout } from '../layout/schema'
// ...
export type ConfigApi = {
  getConfig(): Promise<DashboardConfig>
  saveLayout(layout: DashboardLayout): Promise<{ layout: DashboardLayout }>
}
```

- [ ] **Step 4: Add write helper** (`real/http.ts`, append)

```ts
export async function authFetchJsonWrite<T>(path: string, method: 'POST' | 'PUT', body: unknown): Promise<T> {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    throw new Error(`erro ${res.status} ao chamar ${path}`)
  }
  return res.json()
}
```

- [ ] **Step 5: Real configApi** (`real/configApi.ts`)

```ts
import type { ConfigApi } from '../contracts'
import type { DashboardLayout } from '../../layout/schema'
import { authFetchJson, authFetchJsonWrite } from './http'

export const realConfigApi: ConfigApi = {
  getConfig() {
    return authFetchJson('/config')
  },
  saveLayout(layout: DashboardLayout) {
    return authFetchJsonWrite('/config/layout', 'PUT', { layout })
  },
}
```

- [ ] **Step 6: Mock configApi** (`mock/configApi.ts`)

```ts
import type { ConfigApi } from '../contracts'
import type { DashboardLayout } from '../../layout/schema'

// Estado em memória: prova o round-trip save→get no modo mock.
let _layout: DashboardLayout | null = null

export const mockConfigApi: ConfigApi = {
  async getConfig() {
    // 4000 deliberadamente != fallback 3000 (prova wiring end-to-end).
    return { carousel_interval_ms: 4000, layout: _layout }
  },
  async saveLayout(layout: DashboardLayout) {
    _layout = layout
    return { layout }
  },
}
```

- [ ] **Step 7: Rodar testes, verificar verde**

Run: `npm test -- configApi && npm test -- 'api/index' && npm test -- queries`
Expected: PASS. Consumidores existentes de `getConfig` já auditados: `queries.test.tsx:58` usa `expect(...carousel_interval_ms).toBe(4000)` (assert em campo, não no objeto inteiro) → adicionar `layout` **não quebra**. `real/configApi.test.ts` é substituído neste task. Se algum assert usar `toEqual` no objeto de config inteiro, atualizar para incluir `layout`.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/api/contracts.ts frontend/src/lib/api/real/http.ts frontend/src/lib/api/real/configApi.ts frontend/src/lib/api/mock/configApi.ts frontend/src/lib/api/mock/configApi.test.ts frontend/src/lib/api/real/configApi.test.ts
git commit -m "feat(frontend): ConfigApi.saveLayout (PUT) + getConfig traz layout; mock com round-trip"
```

---

### Task 7: Frontend — `useAuth` expõe `isAdmin`

**Files:**
- Modify: `frontend/src/lib/jwt.ts` (add decode de claim)
- Modify: `frontend/src/lib/useAuth.tsx`
- Test: `frontend/src/lib/useAuth.test.tsx` (Modify), `frontend/src/lib/jwt.test.ts` (Modify)

**Interfaces:**
- Consumes: token JWT em localStorage.
- Produces:
  - `jwt.ts`: `decodeJwtClaim(token: string, claim: string): unknown` (lê um claim do payload; null se inválido).
  - `useAuth()` retorna `{ isAuthenticated, isAdmin, login, logout }` — `isAdmin` derivado do claim `is_admin` do token.

- [ ] **Step 1: Escrever teste falhando** (`jwt.test.ts`, adicionar)

```ts
import { decodeJwtClaim } from './jwt'

function makeToken(payload: object): string {
  const b64 = (o: object) => btoa(JSON.stringify(o)).replace(/=+$/, '')
  return `${b64({ alg: 'HS256' })}.${b64(payload)}.sig`
}

describe('decodeJwtClaim', () => {
  it('lê is_admin true', () => {
    expect(decodeJwtClaim(makeToken({ is_admin: true }), 'is_admin')).toBe(true)
  })
  it('devolve null para token malformado', () => {
    expect(decodeJwtClaim('xxx', 'is_admin')).toBeNull()
  })
})
```

`useAuth.test.tsx` (adicionar caso — seguir o padrão de render existente do arquivo; exemplo):
```ts
it('isAdmin true quando token tem is_admin', () => {
  const b64 = (o: object) => btoa(JSON.stringify(o)).replace(/=+$/, '')
  const exp = Math.floor(Date.now() / 1000) + 3600
  const token = `${b64({ alg: 'HS256' })}.${b64({ is_admin: true, exp })}.sig`
  localStorage.setItem('sentinela_token', token)
  // renderizar com AuthProvider e ler isAdmin via um componente de teste ou renderHook
  // (usar o mesmo utilitário de render já usado neste arquivo)
})
```

(Implementar o caso `useAuth.test.tsx` no mesmo estilo dos testes já presentes no arquivo — se usa `renderHook`, usar `renderHook`. Não inventar utilitário novo.)

- [ ] **Step 2: Rodar teste, verificar que falha**

Run: `npm test -- jwt`
Expected: FAIL — `decodeJwtClaim` não existe.

- [ ] **Step 3: Implementar decode** (`jwt.ts`, append)

```ts
export function decodeJwtClaim(token: string, claim: string): unknown {
  try {
    const payload = token.split('.')[1]
    if (!payload) return null
    const json = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')))
    return json[claim] ?? null
  } catch {
    return null
  }
}
```

- [ ] **Step 4: Expor `isAdmin`** (`useAuth.tsx`)

Adicionar ao `AuthContextValue`: `isAdmin: boolean`. Importar `decodeJwtClaim`. Derivar de `token`:

```tsx
import { decodeJwtExp, decodeJwtClaim } from './jwt'
// ...
type AuthContextValue = {
  isAuthenticated: boolean
  isAdmin: boolean
  login: (usuario: string, senha: string) => Promise<void>
  logout: () => void
}
// dentro do provider:
  const isAdmin = token !== null && decodeJwtClaim(token, 'is_admin') === true
  return (
    <AuthContext.Provider value={{ isAuthenticated: token !== null, isAdmin, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
```

- [ ] **Step 5: Rodar testes, verificar verde**

Run: `npm test -- jwt && npm test -- useAuth`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/jwt.ts frontend/src/lib/jwt.test.ts frontend/src/lib/useAuth.tsx frontend/src/lib/useAuth.test.tsx
git commit -m "feat(frontend): useAuth expõe isAdmin (claim is_admin do JWT)"
```

---

### Task 8: Frontend — `useConfig`/`useSaveLayout` (mutation)

**Files:**
- Modify: `frontend/src/lib/queries.ts`
- Test: `frontend/src/lib/queries.test.tsx` (Modify)

**Interfaces:**
- Consumes: `configApi.saveLayout` (Task 6).
- Produces: `useSaveLayout()` — `useMutation` que chama `configApi.saveLayout`, e no sucesso invalida `['config']`. `useConfig` inalterado (já traz layout via tipo).

- [ ] **Step 1: Escrever teste falhando** (`queries.test.tsx`, adicionar; seguir wrapper QueryClient existente)

```ts
import { renderHook, waitFor } from '@testing-library/react'
import { useSaveLayout } from './queries'
// usar o mesmo createWrapper/QueryClientProvider já presente neste arquivo

it('useSaveLayout chama saveLayout e resolve', async () => {
  const layout = { version: 1 as const, grid: { cols: 12, rowHeight: 40, margin: [8, 8] as [number, number] }, widgets: [] }
  const { result } = renderHook(() => useSaveLayout(), { wrapper: createWrapper() })
  result.current.mutate(layout)
  await waitFor(() => expect(result.current.isSuccess).toBe(true))
})
```

(Modo mock em testes: `mockConfigApi.saveLayout` resolve — sem stub de rede necessário.)

- [ ] **Step 2: Rodar teste, verificar que falha**

Run: `npm test -- queries`
Expected: FAIL — `useSaveLayout` não existe.

- [ ] **Step 3: Implementar** (`queries.ts`, adicionar)

```ts
import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query'
import { metaApi, historyApi, alarmApi, configApi } from './api'
import type { Window } from './types'
import type { DashboardLayout } from './layout/schema'
// ...
export function useSaveLayout() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (layout: DashboardLayout) => configApi.saveLayout(layout),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['config'] }) },
  })
}
```

- [ ] **Step 4: Rodar teste, verificar verde**

Run: `npm test -- queries`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/queries.ts frontend/src/lib/queries.test.tsx
git commit -m "feat(frontend): useSaveLayout (mutation PUT /config/layout, invalida config)"
```

---

### Task 9: Frontend — `KpiWidget` (widget novo)

**Files:**
- Create: `frontend/src/components/widgets/KpiWidget.tsx`
- Create: `frontend/src/components/widgets/KpiWidget.test.tsx`

**Interfaces:**
- Consumes: `useLiveTail(code)` (`{ last }` com `last?.value`, `last?.alarm_state`), `useSensorMeta(code)` (unidade/name), `statusVisuals` para cor.
- Produces: `KpiWidget({ sensorCode, label }: { sensorCode: string; label?: string })` — tile com valor grande, unidade, cor por estado.

- [ ] **Step 1: Escrever teste falhando** (`KpiWidget.test.tsx`)

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { KpiWidget } from './KpiWidget'

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('KpiWidget', () => {
  it('renderiza o label quando fornecido', () => {
    renderWithClient(<KpiWidget sensorCode="PRESS-EXP-01" label="Pressão Expurgo" />)
    expect(screen.getByText('Pressão Expurgo')).toBeInTheDocument()
  })
  it('mostra o sensorCode como fallback de título quando sem label', () => {
    renderWithClient(<KpiWidget sensorCode="PRESS-EXP-01" />)
    expect(screen.getByText(/PRESS-EXP-01/)).toBeInTheDocument()
  })
})
```

(No modo mock, `useSensorMeta`/`useLiveTail` resolvem via mock API. Testes checam o que é estável — label/título. Não fixar o valor numérico live, que é dinâmico no mock.)

- [ ] **Step 2: Rodar teste, verificar que falha**

Run: `npm test -- KpiWidget`
Expected: FAIL.

- [ ] **Step 3: Implementar** (`KpiWidget.tsx`)

```tsx
import { useSensorMeta } from '../../lib/queries'
import { useLiveTail } from '../../lib/useLiveTail'
import { statusVisuals } from '../statusVisuals'

// KPI: valor atual de um sensor em destaque, cor por estado de alarme.
export function KpiWidget({ sensorCode, label }: { sensorCode: string; label?: string }) {
  const meta = useSensorMeta(sensorCode)
  const { last } = useLiveTail(sensorCode)
  const titulo = label ?? meta.data?.name ?? sensorCode
  const unidade = meta.data?.unidade ?? ''
  const state = last?.alarm_state ?? 'ok'
  const cor = statusVisuals(state).color // ajustar ao shape real de statusVisuals

  return (
    <div className="flex h-full flex-col justify-between rounded-lg p-3"
         style={{ background: 'var(--color-surface)' }}>
      <p className="truncate text-xs font-bold uppercase tracking-wide"
         style={{ color: 'var(--color-muted)' }}>{titulo}</p>
      <div className="flex items-baseline gap-1">
        <span className="text-3xl font-bold tabular-nums" style={{ color: cor }}>
          {last?.value ?? '—'}
        </span>
        <span className="text-sm" style={{ color: 'var(--color-muted)' }}>{unidade}</span>
      </div>
    </div>
  )
}
```

Nota ao implementador: **verificar a assinatura real de `statusVisuals`** (arquivo `frontend/src/components/statusVisuals.tsx`) e de `useLiveTail` (retorno `{ last, tail }`) antes de fixar `.color`/`.value`. Ajustar o acesso à cor conforme o que o helper expõe (pode ser `.dot`, `.text`, um token CSS, etc). O teste do Step 1 não depende disso.

- [ ] **Step 4: Rodar teste, verificar verde**

Run: `npm test -- KpiWidget`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/widgets/KpiWidget.tsx frontend/src/components/widgets/KpiWidget.test.tsx
git commit -m "feat(frontend): KpiWidget (valor live de 1 sensor, cor por estado)"
```

---

### Task 10: Frontend — containers adaptadores (Area/Timeseries/Alarms)

**Files:**
- Create: `frontend/src/components/widgets/AreaWidget.tsx`
- Create: `frontend/src/components/widgets/TimeseriesWidget.tsx`
- Create: `frontend/src/components/widgets/AlarmsWidget.tsx`
- Create: `frontend/src/components/widgets/AreaWidget.test.tsx`

**Interfaces:**
- Consumes: hooks existentes (`useSensors`, `useThresholds`, `useLiveStatuses`, `useHistory`, `useLiveTail`, `useAlarms`), `groupSensorsByArea`, componentes `AreaCard`/`TimeSeriesChart`/`AlarmPanel`.
- Produces:
  - `AreaWidget({ areaCode }: { areaCode: string })`
  - `TimeseriesWidget({ sensorCode, defaultWindow }: { sensorCode: string; defaultWindow?: Window })`
  - `AlarmsWidget({ scope, areaCode }: { scope: 'site' | 'area'; areaCode?: string })`

- [ ] **Step 1: Escrever teste falhando** (`AreaWidget.test.tsx`)

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AreaWidget } from './AreaWidget'

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('AreaWidget', () => {
  it('renderiza o AreaCard da área existente no mock', async () => {
    // Descobrir um area_code real do mock: usar o primeiro que aparece.
    renderWithClient(<AreaWidget areaCode="EXPURGO" />)
    // Espera algo do card aparecer (nome da área). Ajustar ao mock real.
    await waitFor(() => expect(screen.getByText(/EXPURGO/i)).toBeInTheDocument())
  })
  it('mostra placeholder quando área não existe', async () => {
    renderWithClient(<AreaWidget areaCode="__NAO_EXISTE__" />)
    await waitFor(() => expect(screen.getByText(/configurar|indisponível|sem dados/i)).toBeInTheDocument())
  })
})
```

Nota: confirmar um `area_code` que existe no mock (`mock/metaApi.ts`) antes de fixar `EXPURGO`. Se o mock usar outro code, usar esse.

- [ ] **Step 2: Rodar teste, verificar que falha**

Run: `npm test -- AreaWidget`
Expected: FAIL.

- [ ] **Step 3: Implementar os três containers**

`AreaWidget.tsx` — monta os props do `AreaCard` a partir do `areaCode`:
```tsx
import { useSensors, useThresholds } from '../../lib/queries'
import { useLiveStatuses } from '../../lib/useLiveStatuses'
import { groupSensorsByArea } from '../../lib/aggregateStatus'
import { AreaCard } from '../AreaCard'
import { useConfig } from '../../lib/queries'
import { WidgetPlaceholder } from './WidgetPlaceholder'

export function AreaWidget({ areaCode }: { areaCode: string }) {
  const sensorsQuery = useSensors()
  const sensors = sensorsQuery.data ?? []
  const codes = sensors.map((s) => s.sensor_code)
  const thresholdResults = useThresholds(codes)
  const thresholdsByCode = Object.fromEntries(codes.map((c, i) => [c, thresholdResults[i]?.data]))
  const liveByCode = useLiveStatuses(codes)
  const config = useConfig()
  const group = groupSensorsByArea(sensors).find((g) => g.area.area_code === areaCode)

  if (!group) return <WidgetPlaceholder texto={`Área "${areaCode}" indisponível`} />

  return (
    <AreaCard
      group={group}
      thresholdsByCode={thresholdsByCode}
      liveByCode={liveByCode}
      selectedSensorCode={null}
      onSelectSensor={() => {}}
      hadAlarmToday={false}
      carouselIntervalMs={config.data?.carousel_interval_ms ?? 3000}
    />
  )
}
```

`TimeseriesWidget.tsx`:
```tsx
import { useState } from 'react'
import { useHistory } from '../../lib/queries'
import { useLiveTail } from '../../lib/useLiveTail'
import { TimeSeriesChart } from '../TimeSeriesChart'
import { WidgetPlaceholder } from './WidgetPlaceholder'
import type { Window } from '../../lib/types'

export function TimeseriesWidget({ sensorCode, defaultWindow = '24h' }: { sensorCode: string; defaultWindow?: Window }) {
  const [window] = useState<Window>(defaultWindow)
  const history = useHistory(sensorCode, window)
  const { tail } = useLiveTail(sensorCode)
  if (!sensorCode) return <WidgetPlaceholder texto="Configurar sensor" />
  // Adaptar props ao TimeSeriesChart real (checar assinatura: history data + tail).
  return <TimeSeriesChart history={history.data} tail={tail} window={window} />
}
```

`AlarmsWidget.tsx`:
```tsx
import { useAlarms, useSensors } from '../../lib/queries'
import { AlarmPanel } from '../AlarmPanel'

export function AlarmsWidget({ scope, areaCode }: { scope: 'site' | 'area'; areaCode?: string }) {
  const alarmsQuery = useAlarms()
  const sensors = useSensors().data ?? []
  const areaNameByCode = Object.fromEntries(sensors.map((s) => [s.area.area_code, s.area.name]))
  const all = alarmsQuery.data ?? []
  const alarms = scope === 'area' && areaCode ? all.filter((a) => a.area_code === areaCode) : all
  return <AlarmPanel alarms={alarms} areaNameByCode={areaNameByCode} onVerMais={() => {}} />
}
```

Criar também `WidgetPlaceholder.tsx`:
```tsx
export function WidgetPlaceholder({ texto }: { texto: string }) {
  return (
    <div className="flex h-full items-center justify-center rounded-lg border border-dashed p-3 text-center text-xs"
         style={{ color: 'var(--color-muted)', borderColor: 'var(--color-muted)' }}>
      {texto}
    </div>
  )
}
```

Nota: **verificar as assinaturas reais** de `TimeSeriesChart` (props) e `AlarmPanel` (já conhecidas: `alarms`, `areaNameByCode`, `onVerMais`) — ajustar. `TimeSeriesChart` exige checagem (não foi extraído); ler `frontend/src/components/TimeSeriesChart.tsx` antes.

- [ ] **Step 4: Rodar teste, verificar verde**

Run: `npm test -- AreaWidget`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/widgets/AreaWidget.tsx frontend/src/components/widgets/TimeseriesWidget.tsx frontend/src/components/widgets/AlarmsWidget.tsx frontend/src/components/widgets/WidgetPlaceholder.tsx frontend/src/components/widgets/AreaWidget.test.tsx
git commit -m "feat(frontend): containers adaptadores Area/Timeseries/Alarms + placeholder"
```

---

### Task 11: Frontend — registry de widgets + `WidgetFrame`

**Files:**
- Create: `frontend/src/lib/widgets/registry.tsx`
- Create: `frontend/src/lib/widgets/registry.test.tsx`
- Create: `frontend/src/components/WidgetFrame.tsx`

**Interfaces:**
- Consumes: containers (Task 9, 10), `WidgetInstance`/`WidgetType` (Task 4).
- Produces:
  - `WIDGET_REGISTRY: Record<WidgetType, WidgetDescriptor>` com `{ type, label, needs, defaultSize, minSize, render(widget) }`.
  - `WidgetFrame({ widget, editing, onConfigure, onRemove }: { widget: WidgetInstance; editing: boolean; onConfigure?: () => void; onRemove?: () => void })`.

- [ ] **Step 1: Escrever teste falhando** (`registry.test.tsx`)

```tsx
import { describe, it, expect } from 'vitest'
import { WIDGET_REGISTRY } from './registry'
import { WIDGET_TYPES } from '../layout/schema'

describe('WIDGET_REGISTRY', () => {
  it('tem descriptor para cada WidgetType', () => {
    for (const t of WIDGET_TYPES) {
      expect(WIDGET_REGISTRY[t]).toBeDefined()
      expect(WIDGET_REGISTRY[t].label).toBeTruthy()
      expect(WIDGET_REGISTRY[t].defaultSize.w).toBeGreaterThan(0)
      expect(['area', 'sensor', 'none']).toContain(WIDGET_REGISTRY[t].needs)
    }
  })
  it('area precisa de area, timeseries/kpi de sensor, alarms de none', () => {
    expect(WIDGET_REGISTRY.area.needs).toBe('area')
    expect(WIDGET_REGISTRY.timeseries.needs).toBe('sensor')
    expect(WIDGET_REGISTRY.kpi.needs).toBe('sensor')
    expect(WIDGET_REGISTRY.alarms.needs).toBe('none')
  })
})
```

- [ ] **Step 2: Rodar teste, verificar que falha**

Run: `npm test -- registry`
Expected: FAIL.

- [ ] **Step 3: Implementar registry** (`registry.tsx`)

```tsx
import type { ReactNode } from 'react'
import type { WidgetInstance, WidgetType } from '../layout/schema'
import { AreaWidget } from '../../components/widgets/AreaWidget'
import { TimeseriesWidget } from '../../components/widgets/TimeseriesWidget'
import { AlarmsWidget } from '../../components/widgets/AlarmsWidget'
import { KpiWidget } from '../../components/widgets/KpiWidget'
import { WidgetPlaceholder } from '../../components/widgets/WidgetPlaceholder'
import type { Window } from '../types'

export type WidgetDescriptor = {
  type: WidgetType
  label: string
  needs: 'area' | 'sensor' | 'none'
  defaultSize: { w: number; h: number }
  minSize: { w: number; h: number }
  render: (widget: WidgetInstance) => ReactNode
}

export const WIDGET_REGISTRY: Record<WidgetType, WidgetDescriptor> = {
  area: {
    type: 'area', label: 'Card de área', needs: 'area',
    defaultSize: { w: 3, h: 3 }, minSize: { w: 2, h: 2 },
    render: (w) => w.binding.areaCode
      ? <AreaWidget areaCode={w.binding.areaCode} />
      : <WidgetPlaceholder texto="Configurar área" />,
  },
  timeseries: {
    type: 'timeseries', label: 'Gráfico temporal', needs: 'sensor',
    defaultSize: { w: 6, h: 4 }, minSize: { w: 3, h: 3 },
    render: (w) => w.binding.sensorCode
      ? <TimeseriesWidget sensorCode={w.binding.sensorCode} defaultWindow={w.options?.defaultWindow as Window | undefined} />
      : <WidgetPlaceholder texto="Configurar sensor" />,
  },
  alarms: {
    type: 'alarms', label: 'Painel de alarmes', needs: 'none',
    defaultSize: { w: 3, h: 6 }, minSize: { w: 2, h: 3 },
    render: (w) => <AlarmsWidget scope={(w.options?.scope as 'site' | 'area') ?? 'site'} areaCode={w.binding.areaCode} />,
  },
  kpi: {
    type: 'kpi', label: 'KPI (valor único)', needs: 'sensor',
    defaultSize: { w: 2, h: 2 }, minSize: { w: 2, h: 2 },
    render: (w) => w.binding.sensorCode
      ? <KpiWidget sensorCode={w.binding.sensorCode} label={w.options?.label as string | undefined} />
      : <WidgetPlaceholder texto="Configurar sensor" />,
  },
}
```

- [ ] **Step 4: Implementar `WidgetFrame`** (`WidgetFrame.tsx`)

```tsx
import type { WidgetInstance } from '../lib/layout/schema'
import { WIDGET_REGISTRY } from '../lib/widgets/registry'

export function WidgetFrame({ widget, editing, onConfigure, onRemove }: {
  widget: WidgetInstance
  editing: boolean
  onConfigure?: () => void
  onRemove?: () => void
}) {
  const descriptor = WIDGET_REGISTRY[widget.type]
  return (
    <div className="relative h-full w-full overflow-hidden">
      {editing && (
        <div className="absolute right-1 top-1 z-10 flex gap-1">
          <button type="button" onClick={onConfigure} aria-label="Configurar widget"
                  className="rounded bg-black/40 px-1.5 text-xs text-white">⚙</button>
          <button type="button" onClick={onRemove} aria-label="Remover widget"
                  className="rounded bg-black/40 px-1.5 text-xs text-white">✕</button>
        </div>
      )}
      {descriptor.render(widget)}
    </div>
  )
}
```

- [ ] **Step 5: Rodar teste, verificar verde + typecheck**

Run: `npm test -- registry && npx tsc -b --noEmit`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/widgets/registry.tsx frontend/src/lib/widgets/registry.test.tsx frontend/src/components/WidgetFrame.tsx
git commit -m "feat(frontend): registry de widgets + WidgetFrame (render + chrome de edição)"
```

---

### Task 12: Frontend — `DashboardGrid` (render read-only + colapso mobile)

**Files:**
- Create: `frontend/src/components/DashboardGrid.tsx`
- Create: `frontend/src/components/DashboardGrid.test.tsx`
- Modify: `frontend/package.json` (add `react-grid-layout`)

**Interfaces:**
- Consumes: `DashboardLayout`, `WidgetInstance` (Task 4); `WidgetFrame` (Task 11).
- Produces: `DashboardGrid({ layout, editing, onLayoutChange, onConfigure, onRemove }: { layout: DashboardLayout; editing: boolean; onLayoutChange?: (l: DashboardLayout) => void; onConfigure?: (id: string) => void; onRemove?: (id: string) => void })`.

- [ ] **Step 1: Adicionar react-grid-layout**

Run (em `frontend/`): `npm install react-grid-layout @types/react-grid-layout`
Se `ERESOLVE` (peer React 19): `npm install react-grid-layout @types/react-grid-layout --legacy-peer-deps`
Expected: pacote instalado. Registrar no commit qual comando foi usado.

Importar o CSS do react-grid-layout uma vez (em `frontend/src/main.tsx` ou no `DashboardGrid.tsx`):
```ts
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'
```

- [ ] **Step 2: Escrever teste falhando** (`DashboardGrid.test.tsx`)

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DashboardGrid } from './DashboardGrid'
import type { DashboardLayout } from '../lib/layout/schema'

const layout: DashboardLayout = {
  version: 1, grid: { cols: 12, rowHeight: 40, margin: [8, 8] },
  widgets: [
    { id: 'k1', type: 'kpi', layout: { x: 0, y: 0, w: 2, h: 2 }, binding: {}, options: {} },
    { id: 'a1', type: 'alarms', layout: { x: 2, y: 0, w: 3, h: 4 }, binding: {}, options: { scope: 'site' } },
  ],
}

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('DashboardGrid', () => {
  it('renderiza um container por widget do layout', () => {
    const { container } = renderWithClient(<DashboardGrid layout={layout} editing={false} />)
    // react-grid-layout marca cada item com a key como data-grid id; checar via .react-grid-item
    expect(container.querySelectorAll('.react-grid-item').length).toBe(2)
  })
  it('em modo edição mostra botões de configurar/remover', () => {
    renderWithClient(<DashboardGrid layout={layout} editing={true} />)
    expect(screen.getAllByLabelText('Remover widget').length).toBe(2)
  })
})
```

- [ ] **Step 3: Rodar teste, verificar que falha**

Run: `npm test -- DashboardGrid`
Expected: FAIL.

- [ ] **Step 4: Implementar** (`DashboardGrid.tsx`)

```tsx
import { Responsive, WidthProvider, type Layout } from 'react-grid-layout'
import type { DashboardLayout } from '../lib/layout/schema'
import { WidgetFrame } from './WidgetFrame'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'

const ResponsiveGridLayout = WidthProvider(Responsive)

export function DashboardGrid({ layout, editing, onLayoutChange, onConfigure, onRemove }: {
  layout: DashboardLayout
  editing: boolean
  onLayoutChange?: (l: DashboardLayout) => void
  onConfigure?: (id: string) => void
  onRemove?: (id: string) => void
}) {
  const rglLayout: Layout[] = layout.widgets.map((w) => ({
    i: w.id, x: w.layout.x, y: w.layout.y, w: w.layout.w, h: w.layout.h,
    minW: w.layout.minW, minH: w.layout.minH,
  }))

  // Mobile: 1 coluna, ordenado por (y,x) — deriva da própria ordem do array já ordenada por y,x.
  const mobileLayout: Layout[] = [...layout.widgets]
    .sort((a, b) => a.layout.y - b.layout.y || a.layout.x - b.layout.x)
    .map((w, i) => ({ i: w.id, x: 0, y: i, w: 1, h: w.layout.h }))

  function handleChange(current: Layout[]) {
    if (!editing || !onLayoutChange) return
    const byId = Object.fromEntries(current.map((l) => [l.i, l]))
    onLayoutChange({
      ...layout,
      widgets: layout.widgets.map((w) => {
        const l = byId[w.id]
        return l ? { ...w, layout: { ...w.layout, x: l.x, y: l.y, w: l.w, h: l.h } } : w
      }),
    })
  }

  return (
    <ResponsiveGridLayout
      className="layout"
      layouts={{ lg: rglLayout, xxs: mobileLayout }}
      breakpoints={{ lg: 768, xxs: 0 }}
      cols={{ lg: layout.grid.cols, xxs: 1 }}
      rowHeight={layout.grid.rowHeight}
      margin={layout.grid.margin}
      isDraggable={editing}
      isResizable={editing}
      onLayoutChange={handleChange}
      draggableCancel="button"
    >
      {layout.widgets.map((w) => (
        <div key={w.id}>
          <WidgetFrame
            widget={w}
            editing={editing}
            onConfigure={onConfigure ? () => onConfigure(w.id) : undefined}
            onRemove={onRemove ? () => onRemove(w.id) : undefined}
          />
        </div>
      ))}
    </ResponsiveGridLayout>
  )
}
```

Nota: `draggableCancel="button"` impede que clicar em ⚙/✕ inicie drag. Verificar no browser (Task 15). Se `.react-grid-item` não aparecer no jsdom (o WidthProvider mede largura, que em jsdom é 0), o teste do Step 2 pode precisar mockar `offsetWidth` ou checar via `data-grid`/keys em vez de classe. Alternativa robusta ao teste: contar `screen.getAllByLabelText('Remover widget')` (só no modo editing) e, no modo leitura, contar por um `data-testid="widget-frame"` adicionado ao `WidgetFrame`. **Se `.react-grid-item` falhar em jsdom, adicionar `data-testid="widget-frame"` no root do `WidgetFrame` e contar por ele** (ajuste pragmático — a verificação visual real fica no Task 15).

- [ ] **Step 5: Rodar teste, verificar verde**

Run: `npm test -- DashboardGrid`
Expected: PASS (aplicar o ajuste de `data-testid` se jsdom não renderizar as classes do RGL).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/DashboardGrid.tsx frontend/src/components/DashboardGrid.test.tsx frontend/package.json frontend/package-lock.json
git commit -m "feat(frontend): DashboardGrid (react-grid-layout, colapso mobile 1 coluna)"
```

---

### Task 13: Frontend — modo edição (palette, config popover, add/remove/save/cancel)

**Files:**
- Create: `frontend/src/components/WidgetPalette.tsx`
- Create: `frontend/src/components/WidgetConfigPopover.tsx`
- Create: `frontend/src/components/DashboardEditor.tsx`
- Create: `frontend/src/components/DashboardEditor.test.tsx`
- Create: `frontend/src/lib/widgets/newWidget.ts` (factory)
- Create: `frontend/src/lib/widgets/newWidget.test.ts`

**Interfaces:**
- Consumes: `WIDGET_REGISTRY`, `DashboardGrid`, `useSaveLayout` (Task 8), `useSensors` (para dropdowns de area/sensor).
- Produces:
  - `newWidget(type, existing): WidgetInstance` — cria instância com `defaultSize`, id único (`${type}-${n}`), posição no fim.
  - `DashboardEditor({ layout, onExit }: { layout: DashboardLayout; onExit: () => void })` — mantém cópia local editável; palette adiciona; popover configura binding/options; salvar via `useSaveLayout`; cancelar chama `onExit`.

- [ ] **Step 1: Escrever teste falhando do factory** (`newWidget.test.ts`)

```ts
import { describe, it, expect } from 'vitest'
import { newWidget } from './newWidget'
import type { DashboardLayout } from '../layout/schema'

const base: DashboardLayout = { version: 1, grid: { cols: 12, rowHeight: 40, margin: [8, 8] }, widgets: [] }

describe('newWidget', () => {
  it('cria kpi com defaultSize e binding vazio', () => {
    const w = newWidget('kpi', base.widgets)
    expect(w.type).toBe('kpi')
    expect(w.layout.w).toBe(2)
    expect(w.binding).toEqual({})
  })
  it('gera ids únicos', () => {
    const w1 = newWidget('kpi', [])
    const w2 = newWidget('kpi', [w1])
    expect(w1.id).not.toBe(w2.id)
  })
})
```

- [ ] **Step 2: Rodar, verificar falha**

Run: `npm test -- newWidget`
Expected: FAIL.

- [ ] **Step 3: Implementar factory** (`newWidget.ts`)

```ts
import type { WidgetInstance, WidgetType } from '../layout/schema'
import { WIDGET_REGISTRY } from './registry'

export function newWidget(type: WidgetType, existing: WidgetInstance[]): WidgetInstance {
  const desc = WIDGET_REGISTRY[type]
  const n = existing.filter((w) => w.type === type).length + 1
  const maxY = existing.reduce((m, w) => Math.max(m, w.layout.y + w.layout.h), 0)
  return {
    id: `${type}-${n}-${maxY}`,
    type,
    layout: { x: 0, y: maxY, w: desc.defaultSize.w, h: desc.defaultSize.h,
              minW: desc.minSize.w, minH: desc.minSize.h },
    binding: {},
    options: type === 'alarms' ? { scope: 'site' } : {},
  }
}
```

- [ ] **Step 4: Rodar, verificar verde**

Run: `npm test -- newWidget`
Expected: PASS.

- [ ] **Step 5: Escrever teste falhando do editor** (`DashboardEditor.test.tsx`)

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DashboardEditor } from './DashboardEditor'
import type { DashboardLayout } from '../lib/layout/schema'

const layout: DashboardLayout = {
  version: 1, grid: { cols: 12, rowHeight: 40, margin: [8, 8] },
  widgets: [{ id: 'k1', type: 'kpi', layout: { x: 0, y: 0, w: 2, h: 2 }, binding: {}, options: {} }],
}

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('DashboardEditor', () => {
  it('adiciona um widget pela palette', async () => {
    renderWithClient(<DashboardEditor layout={layout} onExit={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: /adicionar/i }))
    await userEvent.click(screen.getByRole('button', { name: /card de área/i }))
    // agora deve haver 2 botões de remover (1 original + 1 novo)
    expect(screen.getAllByLabelText('Remover widget').length).toBe(2)
  })
  it('cancelar chama onExit', async () => {
    const onExit = vi.fn()
    renderWithClient(<DashboardEditor layout={layout} onExit={onExit} />)
    await userEvent.click(screen.getByRole('button', { name: /cancelar/i }))
    expect(onExit).toHaveBeenCalled()
  })
})
```

- [ ] **Step 6: Rodar, verificar falha**

Run: `npm test -- DashboardEditor`
Expected: FAIL.

- [ ] **Step 7: Implementar `WidgetPalette`, `WidgetConfigPopover`, `DashboardEditor`**

`WidgetPalette.tsx`:
```tsx
import { WIDGET_REGISTRY } from '../lib/widgets/registry'
import { WIDGET_TYPES } from '../lib/layout/schema'
import type { WidgetType } from '../lib/layout/schema'

export function WidgetPalette({ onAdd }: { onAdd: (type: WidgetType) => void }) {
  return (
    <div className="flex flex-wrap gap-2">
      {WIDGET_TYPES.map((t) => (
        <button key={t} type="button" onClick={() => onAdd(t)}
                className="rounded border px-2 py-1 text-xs"
                style={{ borderColor: 'var(--color-muted)' }}>
          + {WIDGET_REGISTRY[t].label}
        </button>
      ))}
    </div>
  )
}
```

`WidgetConfigPopover.tsx` — dropdown de area/sensor conforme `needs`:
```tsx
import { useSensors } from '../lib/queries'
import { WIDGET_REGISTRY } from '../lib/widgets/registry'
import type { WidgetInstance } from '../lib/layout/schema'

export function WidgetConfigPopover({ widget, onChange, onClose }: {
  widget: WidgetInstance
  onChange: (w: WidgetInstance) => void
  onClose: () => void
}) {
  const sensors = useSensors().data ?? []
  const needs = WIDGET_REGISTRY[widget.type].needs
  const areas = Array.from(new Map(sensors.map((s) => [s.area.area_code, s.area])).values())

  return (
    <div className="rounded-lg border p-3" style={{ background: 'var(--color-surface)' }}>
      {needs === 'area' && (
        <label className="block text-xs">Área
          <select value={widget.binding.areaCode ?? ''}
                  onChange={(e) => onChange({ ...widget, binding: { ...widget.binding, areaCode: e.target.value } })}>
            <option value="">—</option>
            {areas.map((a) => <option key={a.area_code} value={a.area_code}>{a.name}</option>)}
          </select>
        </label>
      )}
      {needs === 'sensor' && (
        <label className="block text-xs">Sensor
          <select value={widget.binding.sensorCode ?? ''}
                  onChange={(e) => onChange({ ...widget, binding: { ...widget.binding, sensorCode: e.target.value } })}>
            <option value="">—</option>
            {sensors.map((s) => <option key={s.sensor_code} value={s.sensor_code}>{s.name}</option>)}
          </select>
        </label>
      )}
      <button type="button" onClick={onClose} className="mt-2 text-xs underline">Fechar</button>
    </div>
  )
}
```

`DashboardEditor.tsx`:
```tsx
import { useState } from 'react'
import { DashboardGrid } from './DashboardGrid'
import { WidgetPalette } from './WidgetPalette'
import { WidgetConfigPopover } from './WidgetConfigPopover'
import { newWidget } from '../lib/widgets/newWidget'
import { useSaveLayout } from '../lib/queries'
import type { DashboardLayout, WidgetType } from '../lib/layout/schema'

export function DashboardEditor({ layout, onExit }: { layout: DashboardLayout; onExit: () => void }) {
  const [draft, setDraft] = useState<DashboardLayout>(layout)
  const [configuring, setConfiguring] = useState<string | null>(null)
  const save = useSaveLayout()

  function addWidget(type: WidgetType) {
    setDraft((d) => ({ ...d, widgets: [...d.widgets, newWidget(type, d.widgets)] }))
  }
  function removeWidget(id: string) {
    setDraft((d) => ({ ...d, widgets: d.widgets.filter((w) => w.id !== id) }))
  }
  function updateWidget(w: WidgetInstanceLike) {
    setDraft((d) => ({ ...d, widgets: d.widgets.map((x) => (x.id === w.id ? w : x)) }))
  }

  const configuringWidget = draft.widgets.find((w) => w.id === configuring) ?? null

  return (
    <div>
      <div className="mb-3 flex items-center gap-3">
        <WidgetPalette onAdd={addWidget} />
        <div className="ml-auto flex gap-2">
          <button type="button" onClick={() => save.mutate(draft, { onSuccess: onExit })}
                  className="rounded px-3 py-1 text-sm font-bold text-white" style={{ background: 'var(--color-primary)' }}>
            Salvar
          </button>
          <button type="button" onClick={onExit} className="rounded border px-3 py-1 text-sm">Cancelar</button>
        </div>
      </div>

      {configuringWidget && (
        <div className="mb-3">
          <WidgetConfigPopover widget={configuringWidget} onChange={updateWidget} onClose={() => setConfiguring(null)} />
        </div>
      )}

      <DashboardGrid
        layout={draft}
        editing
        onLayoutChange={setDraft}
        onConfigure={setConfiguring}
        onRemove={removeWidget}
      />
    </div>
  )
}
```

Nota: `WidgetInstanceLike` acima é ilustrativo — importar `WidgetInstance` de `../lib/layout/schema` e tipar `updateWidget(w: WidgetInstance)`. Corrigir antes de rodar tsc.

- [ ] **Step 8: Rodar testes, verificar verde + typecheck**

Run: `npm test -- DashboardEditor && npx tsc -b --noEmit`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/WidgetPalette.tsx frontend/src/components/WidgetConfigPopover.tsx frontend/src/components/DashboardEditor.tsx frontend/src/components/DashboardEditor.test.tsx frontend/src/lib/widgets/newWidget.ts frontend/src/lib/widgets/newWidget.test.ts
git commit -m "feat(frontend): modo edição (palette, config popover, add/remove/save/cancel)"
```

---

### Task 14: Frontend — integrar no `DashboardPage` (gate por isAdmin)

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Test: `frontend/src/pages/DashboardPage.test.tsx` (Modify)

**Interfaces:**
- Consumes: `useConfig`, `parseLayout`, `defaultLayout`, `DashboardGrid`, `DashboardEditor`, `useAuth().isAdmin`, `groupSensorsByArea`.
- Produces: DashboardPage renderiza layout salvo (ou default) via `DashboardGrid`; botão "Editar" só se `isAdmin`; ao editar, mostra `DashboardEditor`.

- [ ] **Step 1: Escrever teste falhando** (`DashboardPage.test.tsx`, adicionar/ajustar)

```tsx
// Assumindo helper de render com AuthProvider + QueryClient + Router já existente no arquivo.
it('não mostra botão Editar para não-admin', async () => {
  // token sem is_admin (ou sem token). Renderizar e afirmar ausência.
  renderDashboard() // helper do arquivo
  expect(screen.queryByRole('button', { name: /editar/i })).toBeNull()
})

it('mostra botão Editar para admin', async () => {
  const b64 = (o: object) => btoa(JSON.stringify(o)).replace(/=+$/, '')
  const exp = Math.floor(Date.now() / 1000) + 3600
  localStorage.setItem('sentinela_token', `${b64({ alg: 'HS256' })}.${b64({ is_admin: true, exp })}.sig`)
  renderDashboard()
  expect(await screen.findByRole('button', { name: /editar/i })).toBeInTheDocument()
})
```

Nota: adaptar ao helper de render real do arquivo (o teste atual de DashboardPage já monta Providers). Se o arquivo não tem helper reutilizável, seguir o modo como ele monta hoje.

- [ ] **Step 2: Rodar, verificar falha**

Run: `npm test -- DashboardPage`
Expected: FAIL — botão Editar não existe.

- [ ] **Step 3: Refatorar `DashboardPage`**

Substituir o bloco de render do grid hardcoded (o `<div className="grid ...">` com `groups.map(AreaCard)` + `AlarmPanel`) por render via layout. Manter `Topbar`, `ToastContainer`, `DemoBanner`, `AlarmsModal`. Núcleo:

```tsx
import { useMemo, useState } from 'react'
import { useAuth } from '../lib/useAuth'
import { parseLayout } from '../lib/layout/schema'
import { defaultLayout } from '../lib/layout/defaultLayout'
import { DashboardGrid } from '../components/DashboardGrid'
import { DashboardEditor } from '../components/DashboardEditor'
// ... imports existentes mantidos (Topbar, groups, etc.)

export function DashboardPage() {
  const { isAdmin } = useAuth()
  const [editing, setEditing] = useState(false)
  const sensorsQuery = useSensors()
  const configQuery = useConfig()
  const sensors = sensorsQuery.data ?? []
  const groups = groupSensorsByArea(sensors)

  const layout = useMemo(() => {
    return parseLayout(configQuery.data?.layout) ?? defaultLayout(groups)
  }, [configQuery.data?.layout, groups])

  // ... manter healthy/alarms/areaNameByCode/modal como hoje ...

  return (
    <div>
      <Topbar healthy={healthy} unitName={UNIT_NAME} />
      <ToastContainer alarms={alarms} areaNameByCode={areaNameByCode} loaded={!alarmsQuery.isLoading} />
      {isDemoMode() && <DemoBanner simulating={simulating} onSimulate={simulateAlarm} onReset={resetDemo} />}

      <div className="mx-auto max-w-6xl p-4 sm:p-6">
        <div className="mb-2 flex items-center">
          <p className="text-xs font-bold uppercase tracking-wide" style={{ color: 'var(--color-muted)' }}>
            Áreas monitoradas
          </p>
          {isAdmin && !editing && (
            <button type="button" onClick={() => setEditing(true)}
                    className="ml-auto rounded border px-3 py-1 text-sm">Editar</button>
          )}
        </div>

        {editing ? (
          <DashboardEditor layout={layout} onExit={() => setEditing(false)} />
        ) : (
          <DashboardGrid layout={layout} editing={false} />
        )}
      </div>

      {alarmsModalOpen && <AlarmsModal alarms={alarms} areaNameByCode={areaNameByCode} onClose={() => setAlarmsModalOpen(false)} />}
    </div>
  )
}
```

Nota: preservar as funções `simulateAlarm`/`resetDemo`/`isToday`, os hooks de alarmes, e as vars usadas. **Decisão do usuário: dropar o `SensorDetailPanel`/clique-para-detalhe do fluxo principal** — remover o render inline do `SensorDetailPanel`, `window`/`setWindow`, `selectSensor`, `useHistory`/`useLiveTail` do topo da página e imports órfãos (verificar `tsc`/lint). O detalhe agora só existe se um widget `timeseries` for colocado.

**Testes que quebram (auditados via grep) — atualizar neste task:** `src/pages/DashboardPage.test.tsx` tem asserts do layout antigo que serão inválidos:
- `it('...carousel_interval_ms do mock...flui ate o AreaCard...')` — o AreaCard agora renderiza via `AreaWidget` dentro do grid; o `carouselIntervalMs` ainda flui (AreaWidget passa `config.data?.carousel_interval_ms`). Ajustar seletores se o markup do grid mudar a árvore (ex: `within(expurgoCard)`), mantendo a asserção de comportamento do carrossel.
- `it('...Detalhe do sensor...')`, `it('...ao clicar num sensor de outra area...painel de detalhe...')` — **remover** (comportamento dropado).
- Testes de "Alarmes"/"Sentinela"/toasts/modal — devem continuar válidos (Topbar/AlarmPanel/modal preservados); confirmar que `AlarmsWidget` renderiza "Alarmes" no default layout.
- Adicionar os 2 testes novos de gate (Editar visível/oculto) do Step 1.
Rodar a suíte inteira e reconciliar cada vermelho: manter os que testam comportamento preservado, remover os que testam o detalhe dropado.

- [ ] **Step 4: Rodar teste + suíte + typecheck**

Run: `npm test && npx tsc -b --noEmit`
Expected: PASS. Corrigir imports órfãos / testes antigos de DashboardPage que assumiam o grid CSS antigo (atualizar asserts para o novo render).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/DashboardPage.tsx frontend/src/pages/DashboardPage.test.tsx
git commit -m "feat(frontend): DashboardPage renderiza layout (grid/editor), botão Editar gated por isAdmin"
```

---

### Task 15: Verificação real-browser (agent-web / chrome-devtools-mcp)

**Files:** (nenhum de produção — verificação; criar nota de evidência)
- Create: `docs/superpowers/verificacao/2026-07-19-dashboard-customizavel.md`

**Objetivo:** provar end-to-end no browser real (não só jsdom) que o fluxo funciona: carregar dashboard, entrar em edição como admin, adicionar/mover/configurar/remover widget, salvar, recarregar e confirmar persistência (round-trip mock), e colapso mobile.

- [ ] **Step 1: Subir app em modo mock**

Run (em `frontend/`): `npm run dev` (background). Confirmar porta (Vite → 5173+). Modo mock é o default (`VITE_API_MODE` não setado).

- [ ] **Step 2: Simular admin**

No browser (via chrome-devtools-mcp), antes de carregar a página, injetar um token com `is_admin: true` no localStorage key `sentinela_token` (usar `evaluate_script`), com `exp` futuro. Recarregar.

- [ ] **Step 3: Roteiro de verificação** (chrome-devtools-mcp)

Executar e capturar screenshot em cada marco:
1. Navegar para `http://localhost:<porta>/` → dashboard carrega com `defaultLayout` (cards de área + alarms). Screenshot.
2. Clicar "Editar" → aparece palette + Salvar/Cancelar; widgets ganham handles ⚙/✕. Screenshot.
3. Clicar "+ KPI (valor único)" → novo widget aparece. Configurar (⚙) → escolher um sensor no dropdown. Screenshot.
4. Arrastar o KPI para outra posição e redimensionar → confirmar que move/resize responde (drag real, valida react-grid-layout + React 19). Screenshot.
5. Clicar "Salvar" → volta ao modo leitura. Screenshot.
6. Recarregar a página → o KPI adicionado persiste (mock guarda em memória de sessão; enquanto o dev server + aba não reiniciarem, o `_layout` do mock mantém). Confirmar layout preservado. Screenshot. (Nota: reload da aba mantém o módulo JS vivo? Não — reload zera o módulo. Para provar persistência real sem backend, validar o round-trip SEM reload: após Salvar, sair e reentrar em Editar e confirmar o layout salvo. A persistência através de reload só se prova em modo `real` contra a API — cobrir isso como passo opcional 8.)
7. Emular viewport mobile (resize para ~375px) → widgets colapsam em 1 coluna, ordenados. Screenshot.
8. (Opcional, se ambiente real disponível) Rodar `VITE_API_MODE=real` apontando à API+Odoo, repetir Salvar + reload → confirmar persistência através de reload (prova o PUT/GET reais).

- [ ] **Step 4: Registrar evidência**

Escrever `docs/superpowers/verificacao/2026-07-19-dashboard-customizavel.md` com: marcos verificados, o comando de instalação do react-grid-layout usado, quaisquer bugs achados+corrigidos, e os caminhos dos screenshots. Anexar screenshots ao usuário via SendUserFile.

- [ ] **Step 5: Rodar suíte completa final**

Run (em `frontend/`): `npm test && npm run build`
Run (raiz): `pytest api/tests -v`
Expected: tudo verde; build sem erro de tipo.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/verificacao/2026-07-19-dashboard-customizavel.md
git commit -m "docs: evidência de verificação real-browser do dashboard customizável"
```

---

## Self-Review (cobertura do spec)

- **§2 blob no servidor** → Task 1 (Odoo) + Task 3 (API). ✓
- **§3 schema** → Task 4 (zod). ✓
- **§4 registry + KPI** → Task 9, 10, 11. ✓
- **§5 render + defaultLayout + WidgetFrame** → Task 5, 11, 12, 14. ✓
- **§6 modo edição admin** → Task 13, 14 (gate). ✓
- **§7 backend Odoo/API/auth** → Task 1, 2, 3. ✓
- **§8 responsivo colapso mobile** → Task 12 + Task 15 (verificação). ✓
- **§9 unidades** → cada arquivo mapeado em tasks. ✓
- **§10 testes** → cada task tem ciclo TDD; Task 15 = browser. ✓
- **§12 questões abertas:** widget sem binding → placeholder (resolvido: WidgetPlaceholder, Task 9/10/11); cols=12 (default, confirmável no Task 15); react-grid-layout React 19 (risco #1, verificado Task 15). ✓

**Gaps aceitos conscientemente:**
- Teste de 403 para não-admin no PUT depende de usuário não-admin no Odoo; coberto por unit test de `exigir_admin` (Task 2) — anotado.
- Persistência através de reload só provada em modo real (Task 15 passo 8, opcional conforme ambiente).
- **`SensorDetailPanel` (clique-para-detalhe) DROPADO do fluxo principal por decisão explícita do usuário** — detalhe só via widget `timeseries`. Task 14 remove o render e os testes de detalhe. Re-adicionar (como 5º widget ou overlay) é enhancement futuro fora deste plano.
