# Malha de Calibração (E) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modelar a calibração certificada da malha (sensor+conversor) em Odoo — certificado com ganho/offset/validade/histórico — e publicar `cert_ver/cal_ganho/cal_offset` em cada canal do config operacional do Hub, para o coletor carimbar cada leitura.

**Architecture:** Novo model `sensor_monitor.calibracao` (append-only, um registro por certificado). O `sensor` ganha `conversor_tipo` (atributo, §2.1 da spec) e um `calibracao_vigente_id` computed que resolve o certificado válido para hoje **cujo snapshot de conversor casa** com o conversor atual da malha (trocar o conversor invalida o cert — §2.2). O serializer `api/config_publisher.py` passa a emitir os coeficientes vigentes por canal; quando não há cert vigente, emite identidade (`cert_ver=0, ganho=1.0, offset=0.0`) para o hub carimbar sem alterar o valor.

**Tech Stack:** Odoo 18 (addon `afr_sentinela_sensor_monitor`), Python 3.9 (`api/config_publisher.py`, pytest de integração contra Odoo real via XML-RPC).

## Global Constraints

- **NÃO renomear** os campos de map já em produção: `ma_in_min`/`ma_in_max`/`eng_out_min`/`eng_out_max` (spec §2.3 propõe `usa_map/map_*`; decisão travada: manter os nomes atuais e só adicionar calibração).
- Três camadas de transformação NUNCA se misturam — nomes distintos obrigatórios: **map** (`ma_in_*`/`eng_out_*` no sensor), **decode Modbus** (`scale`/`offset` do registrador), **calibração** (`cal_ganho`/`cal_offset` no cert). Help text obrigatório nos forms (spec §2.4).
- Histórico de calibração é **append-only**: certificados antigos nunca apagados (rastreabilidade — leituras passadas referenciam a versão vigente na época).
- Comando de teste do addon: `docker compose exec -T odoo odoo -d sentinela --test-enable --test-tags /afr_sentinela_sensor_monitor -u afr_sentinela_sensor_monitor --db_host=db --db_user=odoo --db_password=odoo --stop-after-init`
- Pytest da API roda da raiz com `.venv` e Odoo real no ar: `source .venv/bin/activate && python -m pytest api/tests/test_config_serializer.py -q`
- TDD, DRY, YAGNI, commits frequentes.

---

### Task 1: Model `sensor_monitor.calibracao` (o certificado)

**Files:**
- Create: `addons/afr_sentinela_sensor_monitor/models/calibracao.py`
- Modify: `addons/afr_sentinela_sensor_monitor/models/__init__.py` (adicionar import — final da lista, após `sensor_rs485_ext`)
- Modify: `addons/afr_sentinela_sensor_monitor/security/ir.model.access.csv` (2 linhas: view + admin)
- Test: `addons/afr_sentinela_sensor_monitor/tests/test_calibracao.py`
- Modify: `addons/afr_sentinela_sensor_monitor/tests/__init__.py` (adicionar `from . import test_calibracao`)

**Interfaces:**
- Produces: model `sensor_monitor.calibracao` com campos `sensor_id` (M2o), `cert_numero` (Char), `versao` (Integer), `cal_ganho` (Float), `cal_offset` (Float), `validade_de` (Date), `validade_ate` (Date), `conversor_tipo_snapshot` (Selection), `empresa_calibracao_id` (M2o res.partner), `documento` (Binary), `estado` (computed Selection `vigente`/`expirado`/`futuro`). Consumido pelas Tasks 2 e 5.

- [ ] **Step 1: Write the failing test**

Criar `addons/afr_sentinela_sensor_monitor/tests/test_calibracao.py`:

```python
from datetime import date, timedelta

from odoo.tests.common import TransactionCase


class TestCalibracao(TransactionCase):
    def _sensor(self):
        site = self.env['sensor_monitor.site'].create({
            'name': 'S', 'site_code': 'SITE-CAL-01', 'vertical': 'cme_hospitalar',
            'partner_id': self.env['res.partner'].create({'name': 'P'}).id})
        hub = self.env['sensor_monitor.hub'].create({
            'name': 'H', 'site_id': site.id, 'hub_code': 'HUB-CAL-01'})
        coletor = self.env['sensor_monitor.coletor'].create({
            'name': 'C', 'hub_id': hub.id, 'coletor_code': 'COL-CAL-01'})
        area = self.env['sensor_monitor.area'].create({
            'name': 'A', 'site_id': site.id, 'area_code': 'AREA-CAL-01',
            'area_category_id': self.env.ref('afr_sentinela_sensor_monitor.area_category_expurgo').id})
        tipo = self.env['sensor_monitor.measurement.type'].search(
            [('code', '=', 'temperatura')], limit=1)
        return self.env['sensor_monitor.sensor'].create({
            'name': 'Sn', 'sensor_code': 'SNR-CAL-01', 'coletor_id': coletor.id,
            'area_id': area.id, 'measurement_type_id': tipo.id, 'protocolo_origem': '4-20ma'})

    def test_certificado_grava_e_computa_estado_vigente(self):
        sensor = self._sensor()
        hoje = date.today()
        cert = self.env['sensor_monitor.calibracao'].create({
            'sensor_id': sensor.id, 'cert_numero': 'CERT-001', 'versao': 1,
            'cal_ganho': 0.965, 'cal_offset': 0.33,
            'validade_de': hoje - timedelta(days=10),
            'validade_ate': hoje + timedelta(days=355),
            'conversor_tipo_snapshot': 'nenhum'})
        assert cert.estado == 'vigente'

    def test_estado_futuro_e_expirado(self):
        sensor = self._sensor()
        hoje = date.today()
        futuro = self.env['sensor_monitor.calibracao'].create({
            'sensor_id': sensor.id, 'cert_numero': 'CERT-F', 'versao': 1,
            'cal_ganho': 1.0, 'cal_offset': 0.0,
            'validade_de': hoje + timedelta(days=5),
            'validade_ate': hoje + timedelta(days=365),
            'conversor_tipo_snapshot': 'nenhum'})
        expirado = self.env['sensor_monitor.calibracao'].create({
            'sensor_id': sensor.id, 'cert_numero': 'CERT-E', 'versao': 2,
            'cal_ganho': 1.0, 'cal_offset': 0.0,
            'validade_de': hoje - timedelta(days=400),
            'validade_ate': hoje - timedelta(days=35),
            'conversor_tipo_snapshot': 'nenhum'})
        assert futuro.estado == 'futuro'
        assert expirado.estado == 'expirado'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T odoo odoo -d sentinela --test-enable --test-tags /afr_sentinela_sensor_monitor -u afr_sentinela_sensor_monitor --db_host=db --db_user=odoo --db_password=odoo --stop-after-init 2>&1 | grep -iE 'FAIL|ERROR|test_calibracao'`
Expected: FAIL — model `sensor_monitor.calibracao` não existe (`KeyError`/`ValueError` no `create`).

> Nota: adicione `from . import test_calibracao` em `tests/__init__.py` e `from . import calibracao` em `models/__init__.py` já neste passo, senão o teste nem carrega.

- [ ] **Step 3: Write minimal implementation**

Criar `addons/afr_sentinela_sensor_monitor/models/calibracao.py`:

```python
from odoo import api, fields, models

CONVERSOR_TIPOS = [
    ('nenhum', 'Nenhum (sensor entrega direto)'),
    ('485_pt100', 'RS-485 PT100'),
    ('485_4_20ma', 'RS-485 4-20mA'),
    ('485_0_30v', 'RS-485 0-30V'),
]


class Calibracao(models.Model):
    _name = 'sensor_monitor.calibracao'
    _description = 'Certificado de Calibração da Malha'
    _order = 'sensor_id, versao desc'

    sensor_id = fields.Many2one(
        'sensor_monitor.sensor', required=True, ondelete='cascade',
        help='A malha certificada (sensor + conversor).')
    cert_numero = fields.Char(help='Número do certificado emitido pela empresa de calibração.')
    versao = fields.Integer(
        required=True, default=1,
        help='Incremental por malha (v1, v2, …). Entra no snapshot de cada leitura.')
    cal_ganho = fields.Float(
        required=True, default=1.0, digits=(16, 6),
        help='Ganho multiplicativo CERTIFICADO, aplicado DEPOIS do map. '
             'Não confundir com o ganho do map nem com o scale do registrador Modbus.')
    cal_offset = fields.Float(
        required=True, default=0.0, digits=(16, 6),
        help='Offset aditivo CERTIFICADO da calibração. Distinto do offset do registrador Modbus.')
    validade_de = fields.Date(required=True)
    validade_ate = fields.Date(required=True)
    conversor_tipo_snapshot = fields.Selection(
        CONVERSOR_TIPOS, required=True, default='nenhum',
        help='Conversor da malha no momento da calibração (a calibração é do par sensor+conversor). '
             'Se o conversor atual do sensor divergir deste snapshot, este certificado deixa de valer.')
    empresa_calibracao_id = fields.Many2one('res.partner', string='Empresa de Calibração')
    documento = fields.Binary(string='Certificado (PDF)')
    documento_nome = fields.Char()
    estado = fields.Selection(
        [('vigente', 'Vigente'), ('expirado', 'Expirado'), ('futuro', 'Futuro')],
        compute='_compute_estado', store=False)

    @api.depends('validade_de', 'validade_ate')
    def _compute_estado(self):
        hoje = fields.Date.context_today(self)
        for cert in self:
            if cert.validade_de and hoje < cert.validade_de:
                cert.estado = 'futuro'
            elif cert.validade_ate and hoje > cert.validade_ate:
                cert.estado = 'expirado'
            else:
                cert.estado = 'vigente'
```

Adicionar em `models/__init__.py` (última linha):

```python
from . import calibracao
```

Adicionar em `security/ir.model.access.csv` (2 linhas novas, seguindo o padrão sensor):

```csv
access_calibracao_view,calibracao.view,model_sensor_monitor_calibracao,group_sensor_monitor_view,1,0,0,0
access_calibracao_admin,calibracao.admin,model_sensor_monitor_calibracao,group_sensor_monitor_admin,1,1,1,1
```

Adicionar em `tests/__init__.py` (última linha):

```python
from . import test_calibracao
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T odoo odoo -d sentinela --test-enable --test-tags /afr_sentinela_sensor_monitor -u afr_sentinela_sensor_monitor --db_host=db --db_user=odoo --db_password=odoo --stop-after-init 2>&1 | grep -iE 'FAIL|ERROR|0 failed|test_calibracao'`
Expected: sem FAIL/ERROR; `test_calibracao` passa.

- [ ] **Step 5: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor/models/calibracao.py \
        addons/afr_sentinela_sensor_monitor/models/__init__.py \
        addons/afr_sentinela_sensor_monitor/security/ir.model.access.csv \
        addons/afr_sentinela_sensor_monitor/tests/test_calibracao.py \
        addons/afr_sentinela_sensor_monitor/tests/__init__.py
git commit -m "feat(calibracao): model sensor_monitor.calibracao com estado computed"
```

---

### Task 2: Sensor — `conversor_tipo` + `calibracao_vigente_id` (cert válido casando conversor)

**Files:**
- Modify: `addons/afr_sentinela_sensor_monitor/models/sensor.py`
- Test: `addons/afr_sentinela_sensor_monitor/tests/test_calibracao.py` (adicionar métodos)

**Interfaces:**
- Consumes: model `sensor_monitor.calibracao` (Task 1).
- Produces: `sensor_monitor.sensor.conversor_tipo` (Selection, mesmos valores `CONVERSOR_TIPOS`), `sensor.calibracao_ids` (One2many), `sensor.calibracao_vigente_id` (Many2one computed → o cert `estado='vigente'` de maior `versao` **cujo `conversor_tipo_snapshot == sensor.conversor_tipo`**; vazio se nenhum casa). Consumido pela Task 5 (config_publisher).

- [ ] **Step 1: Write the failing test**

Adicionar a `tests/test_calibracao.py`:

```python
    def test_vigente_resolve_maior_versao_que_casa_conversor(self):
        sensor = self._sensor()
        sensor.conversor_tipo = 'nenhum'
        hoje = date.today()
        base = {'sensor_id': sensor.id, 'validade_de': hoje - timedelta(days=1),
                'validade_ate': hoje + timedelta(days=365)}
        self.env['sensor_monitor.calibracao'].create(
            {**base, 'cert_numero': 'v1', 'versao': 1, 'cal_ganho': 0.9,
             'cal_offset': 0.0, 'conversor_tipo_snapshot': 'nenhum'})
        v2 = self.env['sensor_monitor.calibracao'].create(
            {**base, 'cert_numero': 'v2', 'versao': 2, 'cal_ganho': 0.965,
             'cal_offset': 0.33, 'conversor_tipo_snapshot': 'nenhum'})
        assert sensor.calibracao_vigente_id == v2

    def test_troca_de_conversor_invalida_cert(self):
        sensor = self._sensor()
        sensor.conversor_tipo = 'nenhum'
        hoje = date.today()
        self.env['sensor_monitor.calibracao'].create({
            'sensor_id': sensor.id, 'cert_numero': 'v1', 'versao': 1,
            'cal_ganho': 0.965, 'cal_offset': 0.33,
            'validade_de': hoje - timedelta(days=1), 'validade_ate': hoje + timedelta(days=365),
            'conversor_tipo_snapshot': 'nenhum'})
        assert sensor.calibracao_vigente_id  # casa
        sensor.conversor_tipo = '485_pt100'  # troca o conversor
        assert not sensor.calibracao_vigente_id  # cert antigo deixa de valer
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T odoo odoo -d sentinela --test-enable --test-tags /afr_sentinela_sensor_monitor -u afr_sentinela_sensor_monitor --db_host=db --db_user=odoo --db_password=odoo --stop-after-init 2>&1 | grep -iE 'FAIL|ERROR'`
Expected: FAIL — `conversor_tipo`/`calibracao_vigente_id` não existem no sensor.

- [ ] **Step 3: Write minimal implementation**

Em `addons/afr_sentinela_sensor_monitor/models/sensor.py`, importar os tipos e adicionar campos. Trocar o topo do arquivo:

```python
from odoo import api, fields, models

from .calibracao import CONVERSOR_TIPOS
from .common import validate_code
```

E dentro da classe `Sensor`, após `ativo = fields.Boolean(default=True)`:

```python
    conversor_tipo = fields.Selection(
        CONVERSOR_TIPOS, default='nenhum', required=True,
        help='Conversor da malha (atributo, não peça rastreada). "Nenhum" = o sensor '
             'entrega o valor direto. Trocar o conversor invalida a calibração vigente.')
    calibracao_ids = fields.One2many(
        'sensor_monitor.calibracao', 'sensor_id', string='Certificados de Calibração')
    calibracao_vigente_id = fields.Many2one(
        'sensor_monitor.calibracao', compute='_compute_calibracao_vigente', store=False,
        help='Certificado cuja janela contém hoje E cujo conversor casa com o atual.')

    @api.depends('conversor_tipo', 'calibracao_ids.validade_de',
                 'calibracao_ids.validade_ate', 'calibracao_ids.conversor_tipo_snapshot',
                 'calibracao_ids.versao')
    def _compute_calibracao_vigente(self):
        hoje = fields.Date.context_today(self)
        for sensor in self:
            candidatos = sensor.calibracao_ids.filtered(
                lambda c: c.conversor_tipo_snapshot == sensor.conversor_tipo
                and c.validade_de and c.validade_ate
                and c.validade_de <= hoje <= c.validade_ate)
            sensor.calibracao_vigente_id = (
                max(candidatos, key=lambda c: c.versao) if candidatos else False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T odoo odoo -d sentinela --test-enable --test-tags /afr_sentinela_sensor_monitor -u afr_sentinela_sensor_monitor --db_host=db --db_user=odoo --db_password=odoo --stop-after-init 2>&1 | grep -iE 'FAIL|ERROR'`
Expected: sem FAIL/ERROR.

- [ ] **Step 5: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor/models/sensor.py \
        addons/afr_sentinela_sensor_monitor/tests/test_calibracao.py
git commit -m "feat(calibracao): conversor_tipo + calibracao_vigente_id no sensor"
```

---

### Task 3: Views — form/list de calibração, menu, aba+help no sensor

**Files:**
- Create: `addons/afr_sentinela_sensor_monitor/views/calibracao_views.xml`
- Modify: `addons/afr_sentinela_sensor_monitor/views/sensor_views.xml` (aba Calibração + campo conversor_tipo + help)
- Modify: `addons/afr_sentinela_sensor_monitor/views/menu.xml` (item Calibrações)
- Modify: `addons/afr_sentinela_sensor_monitor/__manifest__.py` (registrar `views/calibracao_views.xml` antes de `views/menu.xml`)

**Interfaces:**
- Consumes: models das Tasks 1-2. Sem interface de código nova (só UI).

> Views não têm teste unitário; a validação é o addon **carregar sem erro de XML** (o `-u` no comando de teste já falha se a view for inválida). Não há step de "test fail primeiro" — o gate é o upgrade limpo no Step 3.

- [ ] **Step 1: Criar a view de calibração**

Criar `addons/afr_sentinela_sensor_monitor/views/calibracao_views.xml`:

```xml
<odoo>
    <record id="view_calibracao_list" model="ir.ui.view">
        <field name="name">sensor_monitor.calibracao.list</field>
        <field name="model">sensor_monitor.calibracao</field>
        <field name="arch" type="xml">
            <list>
                <field name="sensor_id"/>
                <field name="cert_numero"/>
                <field name="versao"/>
                <field name="cal_ganho"/>
                <field name="cal_offset"/>
                <field name="validade_de"/>
                <field name="validade_ate"/>
                <field name="estado"/>
            </list>
        </field>
    </record>
    <record id="view_calibracao_form" model="ir.ui.view">
        <field name="name">sensor_monitor.calibracao.form</field>
        <field name="model">sensor_monitor.calibracao</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <group>
                        <field name="sensor_id"/>
                        <field name="cert_numero"/>
                        <field name="versao"/>
                        <field name="conversor_tipo_snapshot"/>
                        <field name="estado"/>
                    </group>
                    <group string="Correção certificada (aplicada DEPOIS do map — vem do laboratório, tem validade)">
                        <field name="cal_ganho"/>
                        <field name="cal_offset"/>
                        <field name="validade_de"/>
                        <field name="validade_ate"/>
                    </group>
                    <group>
                        <field name="empresa_calibracao_id"/>
                        <field name="documento" filename="documento_nome"/>
                        <field name="documento_nome" invisible="1"/>
                    </group>
                </sheet>
            </form>
        </field>
    </record>
    <record id="action_calibracao" model="ir.actions.act_window">
        <field name="name">Calibrações</field>
        <field name="res_model">sensor_monitor.calibracao</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

- [ ] **Step 2: Aba Calibração + conversor no form do sensor**

Em `addons/afr_sentinela_sensor_monitor/views/sensor_views.xml`, substituir o `<sheet>...</sheet>` do `view_sensor_form` para adicionar `conversor_tipo` no group principal e uma aba com o histórico. Trocar o bloco:

```xml
                <sheet>
                    <group>
                        <field name="name"/>
                        <field name="sensor_code"/>
                        <field name="coletor_id"/>
                        <field name="area_id"/>
                        <field name="measurement_type_id"/>
                        <field name="protocolo_origem"/>
                        <field name="unidade"/>
                        <field name="ativo"/>
                        <field name="conversor_tipo"/>
                        <field name="modbus_register_id" invisible="protocolo_origem != 'rs485'"/>
                        <field name="modbus_channel" invisible="protocolo_origem != 'rs485'"/>
                        <field name="ma_in_min" invisible="protocolo_origem != 'rs485'"
                               help="Faixa do sinal FÍSICO de entrada (ex. 4 mA). NÃO é calibração."/>
                        <field name="ma_in_max" invisible="protocolo_origem != 'rs485'"
                               help="Faixa do sinal FÍSICO de entrada (ex. 20 mA). NÃO é calibração."/>
                        <field name="eng_out_min" invisible="protocolo_origem != 'rs485'"
                               help="Valor de ENGENHARIA correspondente a ma_in_min (ex. 0 °C)."/>
                        <field name="eng_out_max" invisible="protocolo_origem != 'rs485'"
                               help="Valor de ENGENHARIA correspondente a ma_in_max (ex. 150 °C)."/>
                        <field name="filtro_tipo" invisible="protocolo_origem != 'rs485'"/>
                        <field name="filtro_alpha" invisible="protocolo_origem != 'rs485' or filtro_tipo == 'none'"/>
                    </group>
                    <notebook>
                        <page string="Calibração">
                            <p class="text-muted">
                                Correção CERTIFICADA da malha (ganho/offset do certificado),
                                aplicada DEPOIS do map. Não confundir com a faixa do map acima
                                (sinal físico → engenharia) nem com o scale/offset do registrador
                                Modbus (decode do datasheet). A calibração vem do laboratório e tem validade.
                            </p>
                            <field name="calibracao_vigente_id" readonly="1"/>
                            <field name="calibracao_ids">
                                <list editable="bottom">
                                    <field name="cert_numero"/>
                                    <field name="versao"/>
                                    <field name="conversor_tipo_snapshot"/>
                                    <field name="cal_ganho"/>
                                    <field name="cal_offset"/>
                                    <field name="validade_de"/>
                                    <field name="validade_ate"/>
                                    <field name="estado"/>
                                </list>
                            </field>
                        </page>
                    </notebook>
                </sheet>
```

- [ ] **Step 3: Menu + manifest, e verificar upgrade limpo**

Em `views/menu.xml`, após a linha do `menu_sensor` (sequence 50), adicionar:

```xml
    <menuitem id="menu_calibracao" name="Calibrações" parent="menu_sensor_monitor_cadastro" action="action_calibracao" sequence="55"/>
```

Em `__manifest__.py`, na lista `data`, adicionar `'views/calibracao_views.xml',` **imediatamente antes** de `'views/menu.xml',`.

Run: `docker compose exec -T odoo odoo -d sentinela -u afr_sentinela_sensor_monitor --db_host=db --db_user=odoo --db_password=odoo --stop-after-init 2>&1 | grep -iE 'ERROR|ParseError|Traceback'`
Expected: nenhuma linha (upgrade sem erro de parse/loading das views).

- [ ] **Step 4: Rodar a suite do addon (regressão)**

Run: `docker compose exec -T odoo odoo -d sentinela --test-enable --test-tags /afr_sentinela_sensor_monitor -u afr_sentinela_sensor_monitor --db_host=db --db_user=odoo --db_password=odoo --stop-after-init 2>&1 | grep -iE 'FAIL|ERROR'`
Expected: sem FAIL/ERROR.

- [ ] **Step 5: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor/views/calibracao_views.xml \
        addons/afr_sentinela_sensor_monitor/views/sensor_views.xml \
        addons/afr_sentinela_sensor_monitor/views/menu.xml \
        addons/afr_sentinela_sensor_monitor/__manifest__.py
git commit -m "feat(calibracao): views, menu e aba de calibração no sensor com help anti-confusão"
```

---

### Task 4: Publicar coeficientes de calibração no config operacional do Hub

**Files:**
- Modify: `api/config_publisher.py` (ler `conversor_tipo`/`calibracao_vigente_id` do sensor; emitir bloco `calibracao` por canal)
- Test: `api/tests/test_config_serializer.py` (adicionar caso)

**Interfaces:**
- Consumes: `sensor.calibracao_vigente_id` (Task 2), `sensor_monitor.calibracao.{versao,cal_ganho,cal_offset}` (Task 1).
- **Produces (contrato E→B):** cada `canal` do config publicado ganha a chave
  `'calibracao': {'cert_ver': int, 'ganho': float, 'offset': float}`.
  Quando não há cert vigente: `{'cert_ver': 0, 'ganho': 1.0, 'offset': 0.0}` (identidade).
  **O Plano B (hub) consome exatamente estas chaves** para carimbar `cert_ver|cal_ganho|cal_offset` em cada linha.

- [ ] **Step 1: Write the failing test**

Adicionar a `api/tests/test_config_serializer.py` (usa o helper `_prov_hub_modbus` já existente no arquivo):

```python
def test_canal_carrega_calibracao_vigente():
    from ingestao import odoo_cliente
    from api.config_publisher import serializar_config_hub
    from api.odoo import get_cliente_servico
    cliente = get_cliente_servico()
    hub_code = _prov_hub_modbus(cliente)
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)

    sensor_id = ex('sensor_monitor.sensor', 'search', [('sensor_code', '=', SENSOR_CODE)])[0]
    ex('sensor_monitor.sensor', 'write', [sensor_id], {'conversor_tipo': 'nenhum'})
    # cert vigente casando o conversor 'nenhum'
    ex('sensor_monitor.calibracao', 'create', {
        'sensor_id': sensor_id, 'cert_numero': 'CERT-CFG', 'versao': 7,
        'cal_ganho': 0.965, 'cal_offset': 0.33,
        'validade_de': '2020-01-01', 'validade_ate': '2099-12-31',
        'conversor_tipo_snapshot': 'nenhum'})

    cfg = serializar_config_hub(cliente, hub_code)
    bus = next(b for b in cfg['barramentos'] if b['porta'] == '/dev/ttyUSB0')
    disp = next(d for d in bus['dispositivos'] if d['endereco'] == 1)
    canal = next(c for c in disp['canais'] if c['sensor_id'] == SENSOR_CODE)
    assert canal['calibracao'] == {'cert_ver': 7, 'ganho': 0.965, 'offset': 0.33}


def test_canal_sem_cert_emite_identidade():
    from ingestao import odoo_cliente
    from api.config_publisher import serializar_config_hub
    from api.odoo import get_cliente_servico
    cliente = get_cliente_servico()
    hub_code = _prov_hub_modbus(cliente)
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)
    # garante que o sensor não tem cert casando o conversor atual
    sensor_id = ex('sensor_monitor.sensor', 'search', [('sensor_code', '=', SENSOR_CODE)])[0]
    ex('sensor_monitor.sensor', 'write', [sensor_id], {'conversor_tipo': '485_0_30v'})

    cfg = serializar_config_hub(cliente, hub_code)
    bus = next(b for b in cfg['barramentos'] if b['porta'] == '/dev/ttyUSB0')
    disp = next(d for d in bus['dispositivos'] if d['endereco'] == 1)
    canal = next(c for c in disp['canais'] if c['sensor_id'] == SENSOR_CODE)
    assert canal['calibracao'] == {'cert_ver': 0, 'ganho': 1.0, 'offset': 0.0}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest api/tests/test_config_serializer.py::test_canal_carrega_calibracao_vigente api/tests/test_config_serializer.py::test_canal_sem_cert_emite_identidade -q`
Expected: FAIL — `KeyError: 'calibracao'` (a chave ainda não é emitida).

- [ ] **Step 3: Write minimal implementation**

Em `api/config_publisher.py`, dentro de `serializar_config_hub`:

(a) adicionar `conversor_tipo` e `calibracao_vigente_id` aos `fields=` do `search_read` de sensores (bloco por volta da linha 70-74):

```python
            sensores = ex('sensor_monitor.sensor', 'search_read',
                          [('modbus_register_id', 'in', regs)],
                          fields=['sensor_code', 'modbus_channel', 'ma_in_min', 'ma_in_max',
                                  'eng_out_min', 'eng_out_max', 'filtro_tipo', 'filtro_alpha',
                                  'unidade', 'protocolo_origem', 'area_id', 'measurement_type_id',
                                  'conversor_tipo', 'calibracao_vigente_id'])
```

(b) resolver os certs vigentes em lote (após o bloco `tipos_por_id`, antes de `canais = []`):

```python
            cert_ids = {s['calibracao_vigente_id'][0] for s in sensores if s.get('calibracao_vigente_id')}
            certs_por_id = {}
            if cert_ids:
                certs = ex('sensor_monitor.calibracao', 'read', list(cert_ids),
                           fields=['versao', 'cal_ganho', 'cal_offset'])
                certs_por_id = {c['id']: c for c in certs}
```

(c) emitir o bloco `calibracao` por canal (dentro do `for s in sensores`, adicionar ao dict `canal`):

```python
                cert = certs_por_id.get(s['calibracao_vigente_id'][0]) if s.get('calibracao_vigente_id') else None
                canal['calibracao'] = {
                    'cert_ver': cert['versao'] if cert else 0,
                    'ganho': cert['cal_ganho'] if cert else 1.0,
                    'offset': cert['cal_offset'] if cert else 0.0,
                }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && python -m pytest api/tests/test_config_serializer.py -q`
Expected: PASS (todos, incluindo os pré-existentes — regressão).

- [ ] **Step 5: Commit**

```bash
git add api/config_publisher.py api/tests/test_config_serializer.py
git commit -m "feat(calibracao): publicar cert_ver/ganho/offset vigentes por canal no config do Hub"
```

---

## Self-Review (E)

- **§2.1/2.2 (malha + cert first-class, bundle sem tabela malha):** Tasks 1-2 — cert é model próprio; malha fica como `sensor + conversor_tipo`. ✔
- **§2.2 (trocar conversor invalida cert):** Task 2, `_compute_calibracao_vigente` filtra por `conversor_tipo_snapshot == sensor.conversor_tipo`. ✔
- **§2.2 (append-only):** ⚠️ NÃO garantido na v1. A aba usa `<list editable="bottom">` (permite editar/remover certs inline), o ACL admin dá `unlink`, e `ondelete='cascade'` apaga o histórico ao apagar o sensor. Gap **latente** (nenhuma leitura assinada referencia cert ainda — o stamping por linha é o Plano B). Hardening real (bloquear `write`/`unlink` em cert; `ondelete='restrict'`) fica como follow-up na era do Plano B. Adicionado na fix wave: `unique(sensor_id, versao)` p/ `cert_ver` determinístico.
- **§2.4 (help text anti-confusão):** Task 3 — help em `conversor_tipo`, `ma_in_*`, `eng_out_*`, e nota na aba Calibração. ✔
- **§4.3 (coeficientes por linha):** o *transporte* dos coeficientes até o hub é a Task 4 (contrato E→B). O carimbo por linha é o Plano B. ✔
- **Map naming:** mantidos `ma_in_*`/`eng_out_*`; nada renomeado. ✔
- Tipos consistentes: `calibracao_vigente_id` (M2o) usado na Task 4 via `[0]` (par id/nome do search_read). ✔
