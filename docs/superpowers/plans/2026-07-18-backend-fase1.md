# Backend Fase 1 (módulo Odoo + schema TimescaleDB) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Subir o esqueleto Docker (Odoo 18 + postgres-odoo + TimescaleDB) e implementar o módulo Odoo `afr_sentinela_sensor_monitor` com os 14 modelos, segurança multi-tenant e schema TimescaleDB descritos em `odoo_modelo_dados_spec.md`.

**Architecture:** Módulo Odoo padrão (`models/`, `security/`, `data/`, `views/`, `tests/`) instalado num container `odoo:18.0` oficial via bind-mount de `addons/`; banco do Odoo em container `postgres-odoo` separado; dados temporais de sensor num container `timescaledb` também separado, com schema aplicado via script SQL de init.

**Tech Stack:** Odoo 18 (imagem oficial `odoo:18.0`), PostgreSQL (imagem oficial, banco do Odoo), `timescale/timescaledb-ha:pg16` (TimescaleDB), Docker Compose.

## Global Constraints

- Versão do Odoo: **18** (`odoo:18.0`, sintaxe de view `<list>` em vez de `<tree>`).
- Nome técnico do módulo: **`afr_sentinela_sensor_monitor`**.
- `retention_years` do site: **sempre >= 5** (piso legal RDC 15).
- `file.ledger`: único por (`coletor_id`, `data_referencia`, `tipo_arquivo`).
- `modbus.device`: único por (`rs485_bus_id`, `slave_address`), `slave_address` entre 1 e 247.
- Campos `*_code` (`site_code`, `area_code`, `hub_code`, `coletor_code`, `sensor_code`, `bus_code`): proibidos os caracteres `|`, `\n`, `\r`.
- `alarm.threshold`: `justificativa_desvio` obrigatória quando `is_valor_padrao_regulatorio = False` e o site do sensor tem `vertical = 'cme_hospitalar'`.
- Modelos de referência/lookup (`area.category`, `measurement.type`, `modbus.profile`, `modbus.profile.register`) são globais — sem `ir.rule` de multi-tenant.
- Fora de escopo nesta rodada: serviço de ingestão, MQTT, control plane (lógica de `config_version`), políticas de retenção automática no Timescale, ações automáticas de offboarding.

---

## Task 1: Docker skeleton (Odoo + postgres-odoo + TimescaleDB sobem vazios)

**Files:**
- Create: `docker-compose.yml`
- Create: `conf/odoo.conf`
- Create: `addons/.gitkeep`
- Create: `timescale/init.sql` (vazio nesta task, populado na Task 2)

**Interfaces:**
- Produces: serviço `odoo` acessível em `http://localhost:8189`; banco `postgres-odoo` acessível internamente em `db:5432`; banco `timescaledb` acessível internamente em `timescaledb:5432` e externamente em `localhost:5433`.

- [ ] **Step 1: Criar `conf/odoo.conf`**

```ini
[options]
addons_path = /mnt/extra-addons
admin_passwd = admin_dev_only
db_host = db
db_port = 5432
db_user = odoo
db_password = odoo
db_name = False
```

- [ ] **Step 2: Criar `docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD: odoo
      POSTGRES_DB: postgres
    volumes:
      - odoo-db-data:/var/lib/postgresql/data
    restart: unless-stopped

  odoo:
    image: odoo:18.0
    depends_on:
      - db
    ports:
      - "8189:8069"
    volumes:
      - ./addons:/mnt/extra-addons
      - ./conf:/etc/odoo
      - odoo-filestore:/var/lib/odoo
    restart: unless-stopped

  timescaledb:
    image: timescale/timescaledb-ha:pg16
    environment:
      POSTGRES_USER: sentinela
      POSTGRES_PASSWORD: sentinela
      POSTGRES_DB: sentinela
    ports:
      - "5433:5432"
    volumes:
      - timescale-data:/home/postgres/pgdata/data
      - ./timescale/init.sql:/docker-entrypoint-initdb.d/init.sql
    restart: unless-stopped

volumes:
  odoo-db-data:
  odoo-filestore:
  timescale-data:
```

- [ ] **Step 3: Criar `addons/.gitkeep` e `timescale/init.sql` vazio**

```bash
mkdir -p addons timescale
touch addons/.gitkeep timescale/init.sql
```

- [ ] **Step 4: Subir os containers e verificar Odoo respondendo**

Run: `docker compose up -d && sleep 15 && curl -sf -o /dev/null -w "%{http_code}\n" http://localhost:8189/web/login`
Expected: `200`

- [ ] **Step 5: Criar o banco de dados de desenvolvimento/teste**

Run: `docker compose exec odoo odoo -d sentinela --db_host=db --db_user=odoo --db_password=odoo -i base --stop-after-init`
Expected: termina sem `CRITICAL`/`ERROR` no log, exit code 0.

- [ ] **Step 6: Verificar TimescaleDB respondendo**

Run: `docker compose exec timescaledb psql -U sentinela -d sentinela -c "SELECT extname FROM pg_extension WHERE extname='timescaledb';"`
Expected: uma linha com `timescaledb`.

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml conf/odoo.conf addons/.gitkeep timescale/init.sql
git commit -m "chore: docker skeleton (odoo 18 + postgres-odoo + timescaledb)"
```

---

## Task 2: Schema TimescaleDB (hypertable + agregados contínuos + compressão)

**Files:**
- Modify: `timescale/init.sql`

**Interfaces:**
- Produces: tabela `sensor_reading(time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura)` como hypertable; views materializadas `sensor_reading_hourly` e `sensor_reading_daily`.

- [ ] **Step 1: Escrever o schema em `timescale/init.sql`**

```sql
CREATE TABLE sensor_reading (
    time            TIMESTAMPTZ NOT NULL,
    site_id         TEXT NOT NULL,
    coletor_id      TEXT NOT NULL,
    sensor_id       TEXT NOT NULL,
    area_id         TEXT NOT NULL,
    tipo_medida     TEXT NOT NULL,
    valor           DOUBLE PRECISION NOT NULL,
    unidade         TEXT NOT NULL,
    protocolo_origem TEXT NOT NULL,
    status_leitura  TEXT NOT NULL
);

SELECT create_hypertable('sensor_reading', by_range('time'));
SELECT add_dimension('sensor_reading', by_hash('site_id', 4));

CREATE INDEX idx_sensor_reading_sensor_time ON sensor_reading (sensor_id, time DESC);

ALTER TABLE sensor_reading SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'sensor_id',
    timescaledb.compress_orderby = 'time DESC'
);
SELECT add_compression_policy('sensor_reading', INTERVAL '7 days');

CREATE MATERIALIZED VIEW sensor_reading_hourly
WITH (timescaledb.continuous) AS
SELECT
    sensor_id,
    time_bucket('1 hour', time) AS bucket,
    min(valor) AS valor_min,
    max(valor) AS valor_max,
    avg(valor) AS valor_avg
FROM sensor_reading
GROUP BY sensor_id, bucket
WITH NO DATA;

SELECT add_continuous_aggregate_policy('sensor_reading_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');

CREATE MATERIALIZED VIEW sensor_reading_daily
WITH (timescaledb.continuous) AS
SELECT
    sensor_id,
    time_bucket('1 day', time) AS bucket,
    min(valor) AS valor_min,
    max(valor) AS valor_max,
    avg(valor) AS valor_avg
FROM sensor_reading
GROUP BY sensor_id, bucket
WITH NO DATA;

SELECT add_continuous_aggregate_policy('sensor_reading_daily',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day');
```

- [ ] **Step 2: Recriar o container do Timescale do zero (o init.sql só roda em volume vazio)**

Run: `docker compose down timescaledb && docker volume rm backend-fase1_timescale-data && docker compose up -d timescaledb && sleep 10`

Note: the exact volume name is `<compose-project-name>_timescale-data` — Compose derives the project name from the working directory unless overridden. Confirm with `docker volume ls | grep timescale-data` before removing if the project name might differ.
Expected: container sobe sem erro.

- [ ] **Step 3: Verificar a hypertable e inserir/consultar uma linha de teste**

Run:
```bash
docker compose exec timescaledb psql -U sentinela -d sentinela -c "SELECT hypertable_name FROM timescaledb_information.hypertables;"
docker compose exec timescaledb psql -U sentinela -d sentinela -c "INSERT INTO sensor_reading VALUES (now(), 'SITE-001', 'COL-001', 'SNR-001', 'EXPURGO', 'temperatura', 19.8, 'C', '4-20ma', 'ok');"
docker compose exec timescaledb psql -U sentinela -d sentinela -c "SELECT sensor_id, valor FROM sensor_reading WHERE sensor_id='SNR-001';"
```
Expected: primeira query lista `sensor_reading`; terceira retorna a linha inserida com `valor = 19.8`.

- [ ] **Step 4: Verificar os continuous aggregates existem**

Run: `docker compose exec timescaledb psql -U sentinela -d sentinela -c "SELECT view_name FROM timescaledb_information.continuous_aggregates;"`
Expected: lista `sensor_reading_hourly` e `sensor_reading_daily`.

- [ ] **Step 5: Commit**

```bash
git add timescale/init.sql
git commit -m "feat: schema timescaledb (hypertable sensor_reading + agregados contínuos)"
```

---

## Task 3: Esqueleto do módulo Odoo (manifest vazio, instala sem erro)

**Files:**
- Create: `addons/afr_sentinela_sensor_monitor/__init__.py`
- Create: `addons/afr_sentinela_sensor_monitor/__manifest__.py`
- Create: `addons/afr_sentinela_sensor_monitor/models/__init__.py`
- Create: `addons/afr_sentinela_sensor_monitor/models/common.py`

**Interfaces:**
- Produces: `validate_code(value)` em `models/common.py` — levanta `odoo.exceptions.ValidationError` se `value` contiver `|`, `\n` ou `\r`; usada por todos os modelos com campo `*_code` a partir da Task 5.

- [ ] **Step 1: Criar `addons/afr_sentinela_sensor_monitor/__init__.py`**

```python
from . import models
```

- [ ] **Step 2: Criar `addons/afr_sentinela_sensor_monitor/__manifest__.py`**

```python
{
    'name': 'Sentinela — Monitoramento de Sensores',
    'version': '18.0.1.0.0',
    'category': 'Manufacturing/Maintenance',
    'summary': 'Cadastro e monitoramento de sensores industriais (CME hospitalar e outros verticais)',
    'depends': ['base', 'mail'],
    'data': [],
    'installable': True,
    'application': True,
}
```

- [ ] **Step 3: Criar `addons/afr_sentinela_sensor_monitor/models/__init__.py`**

```python
from . import common
```

- [ ] **Step 4: Criar `addons/afr_sentinela_sensor_monitor/models/common.py`**

```python
from odoo.exceptions import ValidationError

FORBIDDEN_CHARS = ('|', '\n', '\r')


def validate_code(value):
    if value and any(char in value for char in FORBIDDEN_CHARS):
        raise ValidationError(
            "Identificadores não podem conter '|', quebra de linha ou retorno de carro."
        )
```

- [ ] **Step 5: Instalar o módulo e confirmar que sobe sem erro**

Run: `docker compose exec odoo odoo -d sentinela --db_host=db --db_user=odoo --db_password=odoo -i afr_sentinela_sensor_monitor --stop-after-init`
Expected: log sem `CRITICAL`/`ERROR`, exit code 0.

- [ ] **Step 6: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor
git commit -m "feat: esqueleto do módulo afr_sentinela_sensor_monitor"
```

---

## Task 4: Modelos de referência/lookup (`area.category`, `measurement.type`) + dados RDC15

**Files:**
- Create: `addons/afr_sentinela_sensor_monitor/models/area_category.py`
- Create: `addons/afr_sentinela_sensor_monitor/models/measurement_type.py`
- Modify: `addons/afr_sentinela_sensor_monitor/models/__init__.py`
- Create: `addons/afr_sentinela_sensor_monitor/data/area_category_data.xml`
- Create: `addons/afr_sentinela_sensor_monitor/data/measurement_type_data.xml`
- Modify: `addons/afr_sentinela_sensor_monitor/__manifest__.py`
- Create: `addons/afr_sentinela_sensor_monitor/tests/__init__.py`
- Test: `addons/afr_sentinela_sensor_monitor/tests/test_reference_data.py`

**Interfaces:**
- Produces: modelos `sensor_monitor.area.category` (campos `name`, `code`, `vertical`) e `sensor_monitor.measurement.type` (campos `name`, `code`, `unidade_padrao`); registros de dados com `code` = `EXPURGO`, `PREPARO_ESTERILIZACAO`, `DESINFECCAO_QUIMICA` (area.category, `vertical='cme_hospitalar'`) e `code` = `temperatura`, `umidade_relativa`, `pressao_diferencial` (measurement.type).

- [ ] **Step 1: Escrever o teste em `tests/__init__.py` e `tests/test_reference_data.py`**

`tests/__init__.py`:
```python
from . import test_reference_data
```

`tests/test_reference_data.py`:
```python
from odoo.tests.common import TransactionCase


class TestReferenceData(TransactionCase):

    def test_area_category_rdc15_codes_exist(self):
        codes = self.env['sensor_monitor.area.category'].search([]).mapped('code')
        self.assertIn('EXPURGO', codes)
        self.assertIn('PREPARO_ESTERILIZACAO', codes)
        self.assertIn('DESINFECCAO_QUIMICA', codes)

    def test_measurement_type_codes_exist(self):
        codes = self.env['sensor_monitor.measurement.type'].search([]).mapped('code')
        self.assertIn('temperatura', codes)
        self.assertIn('umidade_relativa', codes)
        self.assertIn('pressao_diferencial', codes)

    def test_measurement_type_unidade_padrao(self):
        temp = self.env['sensor_monitor.measurement.type'].search([('code', '=', 'temperatura')])
        self.assertEqual(temp.unidade_padrao, 'C')
```

- [ ] **Step 2: Rodar os testes e confirmar que falham (modelos não existem)**

Run: `docker compose exec odoo odoo -d sentinela --db_host=db --db_user=odoo --db_password=odoo -u afr_sentinela_sensor_monitor --test-enable --stop-after-init --test-tags /afr_sentinela_sensor_monitor`
Expected: falha com `KeyError` ou `ValueError` referente ao modelo `sensor_monitor.area.category` não encontrado.

- [ ] **Step 3: Implementar `models/area_category.py`**

```python
from odoo import fields, models


class AreaCategory(models.Model):
    _name = 'sensor_monitor.area.category'
    _description = 'Categoria de Área'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    vertical = fields.Selection([
        ('cme_hospitalar', 'CME Hospitalar'),
        ('industrial_generico', 'Industrial Genérico'),
    ], required=True)

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Código já cadastrado.'),
    ]
```

- [ ] **Step 4: Implementar `models/measurement_type.py`**

```python
from odoo import fields, models


class MeasurementType(models.Model):
    _name = 'sensor_monitor.measurement.type'
    _description = 'Tipo de Medição'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    unidade_padrao = fields.Char(required=True)

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Código já cadastrado.'),
    ]
```

- [ ] **Step 5: Atualizar `models/__init__.py`**

```python
from . import common
from . import area_category
from . import measurement_type
```

- [ ] **Step 6: Criar `data/area_category_data.xml`**

```xml
<odoo>
    <record id="area_category_expurgo" model="sensor_monitor.area.category">
        <field name="name">Expurgo</field>
        <field name="code">EXPURGO</field>
        <field name="vertical">cme_hospitalar</field>
    </record>
    <record id="area_category_preparo_esterilizacao" model="sensor_monitor.area.category">
        <field name="name">Preparo/Esterilização</field>
        <field name="code">PREPARO_ESTERILIZACAO</field>
        <field name="vertical">cme_hospitalar</field>
    </record>
    <record id="area_category_desinfeccao_quimica" model="sensor_monitor.area.category">
        <field name="name">Desinfecção Química</field>
        <field name="code">DESINFECCAO_QUIMICA</field>
        <field name="vertical">cme_hospitalar</field>
    </record>
</odoo>
```

- [ ] **Step 7: Criar `data/measurement_type_data.xml`**

```xml
<odoo>
    <record id="measurement_type_temperatura" model="sensor_monitor.measurement.type">
        <field name="name">Temperatura</field>
        <field name="code">temperatura</field>
        <field name="unidade_padrao">C</field>
    </record>
    <record id="measurement_type_umidade_relativa" model="sensor_monitor.measurement.type">
        <field name="name">Umidade Relativa</field>
        <field name="code">umidade_relativa</field>
        <field name="unidade_padrao">%UR</field>
    </record>
    <record id="measurement_type_pressao_diferencial" model="sensor_monitor.measurement.type">
        <field name="name">Pressão Diferencial</field>
        <field name="code">pressao_diferencial</field>
        <field name="unidade_padrao">Pa</field>
    </record>
</odoo>
```

- [ ] **Step 8: Atualizar `__manifest__.py`**

```python
    'data': [
        'data/area_category_data.xml',
        'data/measurement_type_data.xml',
    ],
```

- [ ] **Step 9: Rodar os testes e confirmar que passam**

Run: `docker compose exec odoo odoo -d sentinela --db_host=db --db_user=odoo --db_password=odoo -u afr_sentinela_sensor_monitor --test-enable --stop-after-init --test-tags /afr_sentinela_sensor_monitor`
Expected: 3 testes OK, sem `FAIL`/`ERROR`.

- [ ] **Step 10: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor
git commit -m "feat: modelos de referência area.category e measurement.type + dados RDC15"
```

---

## Task 5: Hierarquia principal (`site`, `area`, `hub`, `coletor`, `sensor`)

**Files:**
- Create: `addons/afr_sentinela_sensor_monitor/models/site.py`
- Create: `addons/afr_sentinela_sensor_monitor/models/area.py`
- Create: `addons/afr_sentinela_sensor_monitor/models/hub.py`
- Create: `addons/afr_sentinela_sensor_monitor/models/coletor.py`
- Create: `addons/afr_sentinela_sensor_monitor/models/sensor.py`
- Modify: `addons/afr_sentinela_sensor_monitor/models/__init__.py`
- Modify: `addons/afr_sentinela_sensor_monitor/tests/__init__.py`
- Test: `addons/afr_sentinela_sensor_monitor/tests/test_core_hierarchy.py`

**Interfaces:**
- Consumes: `validate_code` de `models/common.py` (Task 3); `sensor_monitor.area.category` e `sensor_monitor.measurement.type` (Task 4).
- Produces: modelos `sensor_monitor.site`, `sensor_monitor.area`, `sensor_monitor.hub`, `sensor_monitor.coletor`, `sensor_monitor.sensor` com todos os campos da seção 4.3–4.7 da spec. Campo `sensor_monitor.sensor.modbus_register_id` **não** existe ainda (adicionado na Task 9).

- [ ] **Step 1: Escrever `tests/test_core_hierarchy.py`**

```python
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestCoreHierarchy(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Hospital Teste'})
        self.area_category = self.env.ref('afr_sentinela_sensor_monitor.area_category_expurgo')
        self.measurement_type = self.env.ref('afr_sentinela_sensor_monitor.measurement_type_temperatura')

    def _create_site(self, **overrides):
        vals = {
            'name': 'CME Central',
            'partner_id': self.partner.id,
            'site_code': 'SITE-001',
            'vertical': 'cme_hospitalar',
        }
        vals.update(overrides)
        return self.env['sensor_monitor.site'].create(vals)

    def test_site_retention_years_floor(self):
        with self.assertRaises(ValidationError):
            self._create_site(retention_mode='expurgar_apos', retention_years=3)

    def test_site_retention_years_default_ok(self):
        site = self._create_site()
        self.assertEqual(site.retention_years, 5)

    def test_site_code_forbids_pipe(self):
        with self.assertRaises(ValidationError):
            self._create_site(site_code='SITE|001')

    def test_sensor_requires_coletor_and_area(self):
        site = self._create_site()
        area = self.env['sensor_monitor.area'].create({
            'name': 'Expurgo',
            'site_id': site.id,
            'area_category_id': self.area_category.id,
            'area_code': 'AREA-001',
        })
        hub = self.env['sensor_monitor.hub'].create({
            'name': 'Hub 1',
            'site_id': site.id,
            'hub_code': 'HUB-001',
        })
        coletor = self.env['sensor_monitor.coletor'].create({
            'name': 'Coletor 1',
            'hub_id': hub.id,
            'coletor_code': 'COL-001',
            'tipo': 'esp32_wifi',
        })
        sensor = self.env['sensor_monitor.sensor'].create({
            'name': 'Sensor Temp Expurgo',
            'sensor_code': 'SNR-001',
            'coletor_id': coletor.id,
            'area_id': area.id,
            'measurement_type_id': self.measurement_type.id,
            'protocolo_origem': '4-20ma',
        })
        self.assertTrue(sensor.coletor_id)
        self.assertTrue(sensor.area_id)
        with self.assertRaises(ValidationError):
            self.env['sensor_monitor.sensor'].create({
                'name': 'Sensor órfão',
                'sensor_code': 'SNR-002',
                'measurement_type_id': self.measurement_type.id,
                'protocolo_origem': '4-20ma',
            })

    def test_coletor_is_hub_embutido_computed(self):
        site = self._create_site(site_code='SITE-002')
        hub = self.env['sensor_monitor.hub'].create({
            'name': 'Hub 2', 'site_id': site.id, 'hub_code': 'HUB-002',
        })
        coletor = self.env['sensor_monitor.coletor'].create({
            'name': 'Coletor RS485', 'hub_id': hub.id,
            'coletor_code': 'COL-002', 'tipo': 'hub_rs485_embutido',
        })
        self.assertTrue(coletor.is_hub_embutido)
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `docker compose exec odoo odoo -d sentinela --db_host=db --db_user=odoo --db_password=odoo -u afr_sentinela_sensor_monitor --test-enable --stop-after-init --test-tags /afr_sentinela_sensor_monitor`
Expected: falha, modelo `sensor_monitor.site` não encontrado.

- [ ] **Step 3: Implementar `models/site.py`**

```python
from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .common import validate_code


class Site(models.Model):
    _name = 'sensor_monitor.site'
    _description = 'Site/Unidade'

    name = fields.Char(required=True)
    partner_id = fields.Many2one('res.partner', required=True, string='Cliente')
    site_code = fields.Char(required=True)
    endereco = fields.Text()
    timezone = fields.Char(default='America/Sao_Paulo')
    vertical = fields.Selection([
        ('cme_hospitalar', 'CME Hospitalar'),
        ('industrial_generico', 'Industrial Genérico'),
    ], required=True)
    ativo = fields.Boolean(default=True)
    retention_mode = fields.Selection([
        ('indefinida', 'Indefinida'),
        ('expurgar_apos', 'Expurgar após período'),
    ], default='indefinida', required=True)
    retention_years = fields.Integer(default=5, required=True)
    lifecycle_status = fields.Selection([
        ('ativo', 'Ativo'),
        ('offboarding', 'Offboarding'),
        ('arquivado', 'Arquivado'),
        ('expurgado', 'Expurgado'),
    ], default='ativo', required=True)
    offboarding_data = fields.Date()
    export_entregue_em = fields.Date()

    _sql_constraints = [
        ('site_code_unique', 'unique(site_code)', 'Código de site já cadastrado.'),
    ]

    @api.constrains('retention_years')
    def _check_retention_years_floor(self):
        for site in self:
            if site.retention_years < 5:
                raise ValidationError('retention_years não pode ser menor que 5 (piso legal RDC 15).')

    @api.constrains('site_code')
    def _check_site_code(self):
        for site in self:
            validate_code(site.site_code)
```

- [ ] **Step 4: Implementar `models/area.py`**

```python
from odoo import fields, models


class Area(models.Model):
    _name = 'sensor_monitor.area'
    _description = 'Área/Sala'

    name = fields.Char(required=True)
    site_id = fields.Many2one('sensor_monitor.site', required=True)
    area_category_id = fields.Many2one('sensor_monitor.area.category', required=True)
    area_code = fields.Char(required=True)

    _sql_constraints = [
        ('area_code_unique_per_site', 'unique(site_id, area_code)', 'Código de área já usado neste site.'),
    ]
```

- [ ] **Step 5: Implementar `models/hub.py`**

```python
from odoo import api, fields, models

from .common import validate_code


class Hub(models.Model):
    _name = 'sensor_monitor.hub'
    _description = 'Hub (Raspberry Pi)'

    name = fields.Char(required=True)
    site_id = fields.Many2one('sensor_monitor.site', required=True)
    hub_code = fields.Char(required=True)
    modelo_hardware = fields.Selection([
        ('raspberry_pi_3b', 'Raspberry Pi 3B'),
    ], default='raspberry_pi_3b', required=True)
    openvpn_cert_fingerprint = fields.Char()
    possui_secure_element = fields.Boolean(default=True)
    secure_element_pubkey_fingerprint = fields.Char()
    firmware_version = fields.Char()
    status = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('manutencao', 'Manutenção'),
    ], default='offline', required=True)
    ultimo_contato = fields.Datetime()
    config_version_desejada = fields.Integer(default=1)
    config_version_aplicada = fields.Integer(default=0)
    config_version_reportada_em = fields.Datetime()

    _sql_constraints = [
        ('hub_code_unique', 'unique(hub_code)', 'Código de hub já cadastrado.'),
    ]

    @api.constrains('hub_code')
    def _check_hub_code(self):
        for hub in self:
            validate_code(hub.hub_code)
```

- [ ] **Step 6: Implementar `models/coletor.py`**

```python
from odoo import api, fields, models

from .common import validate_code


class Coletor(models.Model):
    _name = 'sensor_monitor.coletor'
    _description = 'Coletor'

    name = fields.Char(required=True)
    hub_id = fields.Many2one('sensor_monitor.hub', required=True)
    coletor_code = fields.Char(required=True)
    tipo = fields.Selection([
        ('esp32_wifi', 'ESP32 WiFi'),
        ('esp32_ethernet', 'ESP32 Ethernet'),
        ('esp32_rs485_externo', 'ESP32 RS-485 Externo'),
        ('hub_rs485_embutido', 'Hub RS-485 Embutido'),
    ], required=True)
    is_hub_embutido = fields.Boolean(compute='_compute_is_hub_embutido', store=True)
    hardware_modelo = fields.Char()
    pubkey_fingerprint = fields.Char()
    firmware_version = fields.Char()
    status = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline'),
    ], default='offline', required=True)
    ultimo_arquivo_recebido = fields.Datetime()
    config_version_desejada = fields.Integer(default=1)
    config_version_aplicada = fields.Integer(default=0)
    config_version_reportada_em = fields.Datetime()

    _sql_constraints = [
        ('coletor_code_unique', 'unique(coletor_code)', 'Código de coletor já cadastrado.'),
    ]

    @api.depends('tipo')
    def _compute_is_hub_embutido(self):
        for coletor in self:
            coletor.is_hub_embutido = coletor.tipo == 'hub_rs485_embutido'

    @api.constrains('coletor_code')
    def _check_coletor_code(self):
        for coletor in self:
            validate_code(coletor.coletor_code)
```

- [ ] **Step 7: Implementar `models/sensor.py`**

```python
from odoo import api, fields, models

from .common import validate_code


class Sensor(models.Model):
    _name = 'sensor_monitor.sensor'
    _description = 'Sensor'

    name = fields.Char(required=True)
    sensor_code = fields.Char(required=True)
    coletor_id = fields.Many2one('sensor_monitor.coletor', required=True)
    area_id = fields.Many2one('sensor_monitor.area', required=True)
    measurement_type_id = fields.Many2one('sensor_monitor.measurement.type', required=True)
    protocolo_origem = fields.Selection([
        ('4-20ma', '4-20mA'),
        ('rs485', 'RS-485'),
        ('i2c', 'I2C'),
    ], required=True)
    unidade = fields.Char()
    ativo = fields.Boolean(default=True)

    _sql_constraints = [
        ('sensor_code_unique', 'unique(sensor_code)', 'Código de sensor já cadastrado.'),
    ]

    @api.constrains('sensor_code')
    def _check_sensor_code(self):
        for sensor in self:
            validate_code(sensor.sensor_code)
```

- [ ] **Step 8: Atualizar `models/__init__.py`**

```python
from . import common
from . import area_category
from . import measurement_type
from . import site
from . import area
from . import hub
from . import coletor
from . import sensor
```

- [ ] **Step 9: Atualizar `tests/__init__.py`**

```python
from . import test_reference_data
from . import test_core_hierarchy
```

- [ ] **Step 10: Rodar os testes e confirmar que passam**

Run: `docker compose exec odoo odoo -d sentinela --db_host=db --db_user=odoo --db_password=odoo -u afr_sentinela_sensor_monitor --test-enable --stop-after-init --test-tags /afr_sentinela_sensor_monitor`
Expected: todos os testes OK.

- [ ] **Step 11: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor
git commit -m "feat: hierarquia principal (site, area, hub, coletor, sensor)"
```

---

## Task 6: `alarm.threshold` (chatter, default RDC15, justificativa obrigatória)

**Files:**
- Create: `addons/afr_sentinela_sensor_monitor/models/alarm_threshold.py`
- Modify: `addons/afr_sentinela_sensor_monitor/models/__init__.py`
- Modify: `addons/afr_sentinela_sensor_monitor/tests/__init__.py`
- Test: `addons/afr_sentinela_sensor_monitor/tests/test_alarm_threshold.py`

**Interfaces:**
- Consumes: `sensor_monitor.sensor` (Task 5), `sensor_monitor.area.category` / `sensor_monitor.measurement.type` codes `EXPURGO`/`PREPARO_ESTERILIZACAO` e `temperatura`/`pressao_diferencial` (Task 4).
- Produces: modelo `sensor_monitor.alarm.threshold` com `create()` que preenche `limite_min`/`limite_max`/`is_valor_padrao_regulatorio` a partir da tabela RDC15 quando não informados explicitamente.

- [ ] **Step 1: Escrever `tests/test_alarm_threshold.py`**

```python
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestAlarmThreshold(TransactionCase):

    def setUp(self):
        super().setUp()
        partner = self.env['res.partner'].create({'name': 'Hospital Teste'})
        site = self.env['sensor_monitor.site'].create({
            'name': 'CME Central', 'partner_id': partner.id,
            'site_code': 'SITE-010', 'vertical': 'cme_hospitalar',
        })
        area = self.env['sensor_monitor.area'].create({
            'name': 'Expurgo', 'site_id': site.id,
            'area_category_id': self.env.ref('afr_sentinela_sensor_monitor.area_category_expurgo').id,
            'area_code': 'AREA-010',
        })
        hub = self.env['sensor_monitor.hub'].create({
            'name': 'Hub', 'site_id': site.id, 'hub_code': 'HUB-010',
        })
        coletor = self.env['sensor_monitor.coletor'].create({
            'name': 'Coletor', 'hub_id': hub.id, 'coletor_code': 'COL-010', 'tipo': 'esp32_wifi',
        })
        self.sensor = self.env['sensor_monitor.sensor'].create({
            'name': 'Sensor Temp', 'sensor_code': 'SNR-010',
            'coletor_id': coletor.id, 'area_id': area.id,
            'measurement_type_id': self.env.ref('afr_sentinela_sensor_monitor.measurement_type_temperatura').id,
            'protocolo_origem': '4-20ma',
        })

    def test_rdc15_default_prefill_expurgo_temperatura(self):
        threshold = self.env['sensor_monitor.alarm.threshold'].create({'sensor_id': self.sensor.id})
        self.assertEqual(threshold.limite_min, 18.0)
        self.assertEqual(threshold.limite_max, 22.0)
        self.assertTrue(threshold.is_valor_padrao_regulatorio)

    def test_desvio_requires_justificativa(self):
        with self.assertRaises(ValidationError):
            self.env['sensor_monitor.alarm.threshold'].create({
                'sensor_id': self.sensor.id,
                'limite_min': 10.0,
                'limite_max': 30.0,
                'is_valor_padrao_regulatorio': False,
            })

    def test_desvio_with_justificativa_ok(self):
        threshold = self.env['sensor_monitor.alarm.threshold'].create({
            'sensor_id': self.sensor.id,
            'limite_min': 10.0,
            'limite_max': 30.0,
            'is_valor_padrao_regulatorio': False,
            'justificativa_desvio': 'Ajuste solicitado pela engenharia clínica.',
        })
        self.assertEqual(threshold.limite_min, 10.0)

    def test_unique_threshold_per_sensor(self):
        self.env['sensor_monitor.alarm.threshold'].create({'sensor_id': self.sensor.id})
        with self.assertRaises(Exception):
            self.env['sensor_monitor.alarm.threshold'].create({'sensor_id': self.sensor.id})
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `docker compose exec odoo odoo -d sentinela --db_host=db --db_user=odoo --db_password=odoo -u afr_sentinela_sensor_monitor --test-enable --stop-after-init --test-tags /afr_sentinela_sensor_monitor`
Expected: falha, modelo `sensor_monitor.alarm.threshold` não encontrado.

- [ ] **Step 3: Implementar `models/alarm_threshold.py`**

```python
from odoo import api, fields, models
from odoo.exceptions import ValidationError

RDC15_DEFAULTS = {
    ('EXPURGO', 'temperatura'): (18.0, 22.0),
    ('EXPURGO', 'pressao_diferencial'): (None, -2.5),
    ('PREPARO_ESTERILIZACAO', 'temperatura'): (20.0, 24.0),
    ('PREPARO_ESTERILIZACAO', 'pressao_diferencial'): (2.5, None),
}


class AlarmThreshold(models.Model):
    _name = 'sensor_monitor.alarm.threshold'
    _inherit = ['mail.thread']
    _description = 'Limiar de Alarme'

    sensor_id = fields.Many2one('sensor_monitor.sensor', required=True)
    limite_min = fields.Float(tracking=True)
    limite_max = fields.Float(tracking=True)
    is_valor_padrao_regulatorio = fields.Boolean(default=False)
    origem_ultima_alteracao = fields.Selection([
        ('hub', 'Hub'),
        ('nuvem', 'Nuvem'),
    ], default='nuvem')
    justificativa_desvio = fields.Text()

    _sql_constraints = [
        ('sensor_id_unique', 'unique(sensor_id)', 'Já existe um limiar cadastrado para este sensor.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'limite_min' not in vals and 'limite_max' not in vals:
                sensor = self.env['sensor_monitor.sensor'].browse(vals['sensor_id'])
                key = (sensor.area_id.area_category_id.code, sensor.measurement_type_id.code)
                default = RDC15_DEFAULTS.get(key)
                if default:
                    vals['limite_min'], vals['limite_max'] = default
                    vals['is_valor_padrao_regulatorio'] = True
        return super().create(vals_list)

    @api.constrains('is_valor_padrao_regulatorio', 'justificativa_desvio', 'sensor_id')
    def _check_justificativa_desvio(self):
        for threshold in self:
            vertical = threshold.sensor_id.area_id.site_id.vertical
            if not threshold.is_valor_padrao_regulatorio and vertical == 'cme_hospitalar':
                if not threshold.justificativa_desvio:
                    raise ValidationError(
                        'Desvio do padrão regulatório exige justificativa preenchida.'
                    )
```

- [ ] **Step 4: Atualizar `models/__init__.py`**

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
```

- [ ] **Step 5: Atualizar `tests/__init__.py`**

```python
from . import test_reference_data
from . import test_core_hierarchy
from . import test_alarm_threshold
```

- [ ] **Step 6: Rodar os testes e confirmar que passam**

Run: `docker compose exec odoo odoo -d sentinela --db_host=db --db_user=odoo --db_password=odoo -u afr_sentinela_sensor_monitor --test-enable --stop-after-init --test-tags /afr_sentinela_sensor_monitor`
Expected: todos os testes OK.

- [ ] **Step 7: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor
git commit -m "feat: alarm.threshold com default RDC15 e justificativa obrigatória"
```

---

## Task 7: `alarm.event`

**Files:**
- Create: `addons/afr_sentinela_sensor_monitor/models/alarm_event.py`
- Modify: `addons/afr_sentinela_sensor_monitor/models/__init__.py`
- Modify: `addons/afr_sentinela_sensor_monitor/tests/__init__.py`
- Test: `addons/afr_sentinela_sensor_monitor/tests/test_alarm_event.py`

**Interfaces:**
- Consumes: `sensor_monitor.sensor`, `sensor_monitor.area`, `sensor_monitor.coletor` (Task 5).
- Produces: modelo `sensor_monitor.alarm.event`.

- [ ] **Step 1: Escrever `tests/test_alarm_event.py`**

```python
from odoo.tests.common import TransactionCase


class TestAlarmEvent(TransactionCase):

    def setUp(self):
        super().setUp()
        partner = self.env['res.partner'].create({'name': 'Hospital Teste'})
        site = self.env['sensor_monitor.site'].create({
            'name': 'CME Central', 'partner_id': partner.id,
            'site_code': 'SITE-020', 'vertical': 'cme_hospitalar',
        })
        self.area = self.env['sensor_monitor.area'].create({
            'name': 'Expurgo', 'site_id': site.id,
            'area_category_id': self.env.ref('afr_sentinela_sensor_monitor.area_category_expurgo').id,
            'area_code': 'AREA-020',
        })
        hub = self.env['sensor_monitor.hub'].create({
            'name': 'Hub', 'site_id': site.id, 'hub_code': 'HUB-020',
        })
        self.coletor = self.env['sensor_monitor.coletor'].create({
            'name': 'Coletor', 'hub_id': hub.id, 'coletor_code': 'COL-020', 'tipo': 'esp32_wifi',
        })
        self.sensor = self.env['sensor_monitor.sensor'].create({
            'name': 'Sensor Temp', 'sensor_code': 'SNR-020',
            'coletor_id': self.coletor.id, 'area_id': self.area.id,
            'measurement_type_id': self.env.ref('afr_sentinela_sensor_monitor.measurement_type_temperatura').id,
            'protocolo_origem': '4-20ma',
        })

    def test_create_alarm_event_defaults_status_aberto(self):
        event = self.env['sensor_monitor.alarm.event'].create({
            'sensor_id': self.sensor.id,
            'area_id': self.area.id,
            'coletor_id': self.coletor.id,
            'timestamp_deteccao': '2026-07-16 03:14:00',
            'tipo_violacao': 'abaixo_limite',
            'valor_lido': 1.8,
            'limite_configurado_snapshot': 2.5,
        })
        self.assertEqual(event.status, 'aberto')

    def test_resolver_evento(self):
        event = self.env['sensor_monitor.alarm.event'].create({
            'sensor_id': self.sensor.id,
            'area_id': self.area.id,
            'coletor_id': self.coletor.id,
            'timestamp_deteccao': '2026-07-16 03:14:00',
            'tipo_violacao': 'abaixo_limite',
            'valor_lido': 1.8,
            'limite_configurado_snapshot': 2.5,
        })
        event.write({'status': 'resolvido', 'data_resolucao': '2026-07-16 03:30:00'})
        self.assertEqual(event.status, 'resolvido')
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `docker compose exec odoo odoo -d sentinela --db_host=db --db_user=odoo --db_password=odoo -u afr_sentinela_sensor_monitor --test-enable --stop-after-init --test-tags /afr_sentinela_sensor_monitor`
Expected: falha, modelo `sensor_monitor.alarm.event` não encontrado.

- [ ] **Step 3: Implementar `models/alarm_event.py`**

```python
from odoo import fields, models


class AlarmEvent(models.Model):
    _name = 'sensor_monitor.alarm.event'
    _inherit = ['mail.thread']
    _description = 'Evento de Alarme'

    sensor_id = fields.Many2one('sensor_monitor.sensor')
    area_id = fields.Many2one('sensor_monitor.area')
    coletor_id = fields.Many2one('sensor_monitor.coletor')
    timestamp_deteccao = fields.Datetime(required=True)
    timestamp_resolucao_sensor = fields.Datetime()
    valor_lido = fields.Float()
    tipo_violacao = fields.Selection([
        ('acima_limite', 'Acima do limite'),
        ('abaixo_limite', 'Abaixo do limite'),
        ('sensor_offline', 'Sensor offline'),
        ('erro_leitura', 'Erro de leitura'),
    ], required=True)
    limite_configurado_snapshot = fields.Float()
    origem_arquivo_hash = fields.Char()
    status = fields.Selection([
        ('aberto', 'Aberto'),
        ('reconhecido', 'Reconhecido'),
        ('resolvido', 'Resolvido'),
    ], default='aberto', required=True, tracking=True)
    usuario_responsavel_id = fields.Many2one('res.users')
    data_resolucao = fields.Datetime()
    observacoes = fields.Text()
```

- [ ] **Step 4: Atualizar `models/__init__.py`** (adicionar `from . import alarm_event` ao final)

- [ ] **Step 5: Atualizar `tests/__init__.py`** (adicionar `from . import test_alarm_event` ao final)

- [ ] **Step 6: Rodar os testes e confirmar que passam**

Run: `docker compose exec odoo odoo -d sentinela --db_host=db --db_user=odoo --db_password=odoo -u afr_sentinela_sensor_monitor --test-enable --stop-after-init --test-tags /afr_sentinela_sensor_monitor`
Expected: todos os testes OK.

- [ ] **Step 7: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor
git commit -m "feat: modelo alarm.event"
```

---

## Task 8: `file.ledger` + cron de detecção de lacuna

**Files:**
- Create: `addons/afr_sentinela_sensor_monitor/models/file_ledger.py`
- Create: `addons/afr_sentinela_sensor_monitor/data/file_ledger_cron_data.xml`
- Modify: `addons/afr_sentinela_sensor_monitor/models/__init__.py`
- Modify: `addons/afr_sentinela_sensor_monitor/tests/__init__.py`
- Modify: `addons/afr_sentinela_sensor_monitor/__manifest__.py`
- Test: `addons/afr_sentinela_sensor_monitor/tests/test_file_ledger.py`

**Interfaces:**
- Consumes: `sensor_monitor.coletor`, `sensor_monitor.hub` (Task 5).
- Produces: modelo `sensor_monitor.file.ledger`; método `_cron_detect_gaps()` que cria registros `status_validacao='faltante'` para dias sem ledger entre o primeiro e o último dia conhecido de cada coletor, por `tipo_arquivo`.

- [ ] **Step 1: Escrever `tests/test_file_ledger.py`**

```python
from odoo.tests.common import TransactionCase


class TestFileLedger(TransactionCase):

    def setUp(self):
        super().setUp()
        partner = self.env['res.partner'].create({'name': 'Hospital Teste'})
        site = self.env['sensor_monitor.site'].create({
            'name': 'CME Central', 'partner_id': partner.id,
            'site_code': 'SITE-030', 'vertical': 'cme_hospitalar',
        })
        self.hub = self.env['sensor_monitor.hub'].create({
            'name': 'Hub', 'site_id': site.id, 'hub_code': 'HUB-030',
        })
        self.coletor = self.env['sensor_monitor.coletor'].create({
            'name': 'Coletor', 'hub_id': self.hub.id, 'coletor_code': 'COL-030', 'tipo': 'esp32_wifi',
        })

    def test_unique_ledger_per_coletor_dia_tipo(self):
        self.env['sensor_monitor.file.ledger'].create({
            'coletor_id': self.coletor.id, 'tipo_arquivo': 'leituras',
            'data_referencia': '2026-07-16', 'status_validacao': 'valido',
        })
        with self.assertRaises(Exception):
            self.env['sensor_monitor.file.ledger'].create({
                'coletor_id': self.coletor.id, 'tipo_arquivo': 'leituras',
                'data_referencia': '2026-07-16', 'status_validacao': 'valido',
            })

    def test_hub_id_denormalizado(self):
        ledger = self.env['sensor_monitor.file.ledger'].create({
            'coletor_id': self.coletor.id, 'tipo_arquivo': 'alarmes',
            'data_referencia': '2026-07-16', 'status_validacao': 'valido',
        })
        self.assertEqual(ledger.hub_id, self.hub)

    def test_cron_detect_gaps_creates_missing_entry(self):
        self.env['sensor_monitor.file.ledger'].create({
            'coletor_id': self.coletor.id, 'tipo_arquivo': 'leituras',
            'data_referencia': '2026-07-14', 'status_validacao': 'valido',
        })
        self.env['sensor_monitor.file.ledger'].create({
            'coletor_id': self.coletor.id, 'tipo_arquivo': 'leituras',
            'data_referencia': '2026-07-16', 'status_validacao': 'valido',
        })
        self.env['sensor_monitor.file.ledger']._cron_detect_gaps()
        gap = self.env['sensor_monitor.file.ledger'].search([
            ('coletor_id', '=', self.coletor.id),
            ('tipo_arquivo', '=', 'leituras'),
            ('data_referencia', '=', '2026-07-15'),
        ])
        self.assertEqual(len(gap), 1)
        self.assertEqual(gap.status_validacao, 'faltante')
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `docker compose exec odoo odoo -d sentinela --db_host=db --db_user=odoo --db_password=odoo -u afr_sentinela_sensor_monitor --test-enable --stop-after-init --test-tags /afr_sentinela_sensor_monitor`
Expected: falha, modelo `sensor_monitor.file.ledger` não encontrado.

- [ ] **Step 3: Implementar `models/file_ledger.py`**

```python
from datetime import timedelta

from odoo import fields, models


class FileLedger(models.Model):
    _name = 'sensor_monitor.file.ledger'
    _description = 'Ledger de Recebimento de Arquivo'

    coletor_id = fields.Many2one('sensor_monitor.coletor', required=True)
    hub_id = fields.Many2one('sensor_monitor.hub', related='coletor_id.hub_id', store=True)
    tipo_arquivo = fields.Selection([
        ('leituras', 'Leituras'),
        ('alarmes', 'Alarmes'),
    ], required=True)
    data_referencia = fields.Date(required=True)
    hash_final = fields.Char()
    assinatura = fields.Char()
    horario_recebimento = fields.Datetime()
    status_validacao = fields.Selection([
        ('valido', 'Válido'),
        ('invalido', 'Inválido'),
        ('pendente', 'Pendente'),
        ('faltante', 'Faltante'),
    ], default='pendente', required=True)
    motivo_rejeicao = fields.Text()
    total_linhas = fields.Integer(default=0)

    _sql_constraints = [
        ('unique_coletor_dia_tipo', 'unique(coletor_id, data_referencia, tipo_arquivo)',
         'Já existe um registro de ledger para este coletor/dia/tipo de arquivo.'),
    ]

    def _cron_detect_gaps(self):
        for coletor in self.env['sensor_monitor.coletor'].search([]):
            for tipo in ('leituras', 'alarmes'):
                entries = self.search([
                    ('coletor_id', '=', coletor.id), ('tipo_arquivo', '=', tipo),
                ], order='data_referencia asc')
                if len(entries) < 2:
                    continue
                known_dates = set(entries.mapped('data_referencia'))
                current = entries[0].data_referencia
                last = entries[-1].data_referencia
                while current <= last:
                    if current not in known_dates:
                        self.create({
                            'coletor_id': coletor.id, 'tipo_arquivo': tipo,
                            'data_referencia': current, 'status_validacao': 'faltante',
                        })
                    current += timedelta(days=1)
```

- [ ] **Step 4: Criar `data/file_ledger_cron_data.xml`**

```xml
<odoo>
    <record id="cron_file_ledger_detect_gaps" model="ir.cron">
        <field name="name">Sensor Monitor: detectar lacunas no ledger</field>
        <field name="model_id" ref="model_sensor_monitor_file_ledger"/>
        <field name="state">code</field>
        <field name="code">model._cron_detect_gaps()</field>
        <field name="interval_number">1</field>
        <field name="interval_type">days</field>
        <field name="active">True</field>
    </record>
</odoo>
```

- [ ] **Step 5: Atualizar `models/__init__.py`** (adicionar `from . import file_ledger`)

- [ ] **Step 6: Atualizar `tests/__init__.py`** (adicionar `from . import test_file_ledger`)

- [ ] **Step 7: Atualizar `__manifest__.py`**

```python
    'data': [
        'data/area_category_data.xml',
        'data/measurement_type_data.xml',
        'data/file_ledger_cron_data.xml',
    ],
```

- [ ] **Step 8: Rodar os testes e confirmar que passam**

Run: `docker compose exec odoo odoo -d sentinela --db_host=db --db_user=odoo --db_password=odoo -u afr_sentinela_sensor_monitor --test-enable --stop-after-init --test-tags /afr_sentinela_sensor_monitor`
Expected: todos os testes OK.

- [ ] **Step 9: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor
git commit -m "feat: file.ledger com unicidade e cron de detecção de lacuna"
```

---

## Task 9: Ramo RS-485/Modbus (`rs485.bus`, `modbus.profile`, `modbus.profile.register`, `modbus.device`) + extensão do sensor

**Files:**
- Create: `addons/afr_sentinela_sensor_monitor/models/rs485_bus.py`
- Create: `addons/afr_sentinela_sensor_monitor/models/modbus_profile.py`
- Create: `addons/afr_sentinela_sensor_monitor/models/modbus_device.py`
- Create: `addons/afr_sentinela_sensor_monitor/models/sensor_rs485_ext.py`
- Modify: `addons/afr_sentinela_sensor_monitor/models/__init__.py`
- Modify: `addons/afr_sentinela_sensor_monitor/tests/__init__.py`
- Test: `addons/afr_sentinela_sensor_monitor/tests/test_rs485_modbus.py`

**Interfaces:**
- Consumes: `validate_code` (Task 3), `sensor_monitor.hub` (Task 5), `sensor_monitor.sensor` (Task 5, estendido aqui), `sensor_monitor.measurement.type` (Task 4).
- Produces: modelos `sensor_monitor.rs485.bus`, `sensor_monitor.modbus.profile`, `sensor_monitor.modbus.profile.register`, `sensor_monitor.modbus.device`; campo `sensor_monitor.sensor.modbus_register_id` (Many2one para `sensor_monitor.modbus.profile.register`), com constraint: só pode ser preenchido quando `protocolo_origem = 'rs485'`.

- [ ] **Step 1: Escrever `tests/test_rs485_modbus.py`**

```python
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestRs485Modbus(TransactionCase):

    def setUp(self):
        super().setUp()
        partner = self.env['res.partner'].create({'name': 'Hospital Teste'})
        site = self.env['sensor_monitor.site'].create({
            'name': 'CME Central', 'partner_id': partner.id,
            'site_code': 'SITE-040', 'vertical': 'cme_hospitalar',
        })
        self.area = self.env['sensor_monitor.area'].create({
            'name': 'Expurgo', 'site_id': site.id,
            'area_category_id': self.env.ref('afr_sentinela_sensor_monitor.area_category_expurgo').id,
            'area_code': 'AREA-040',
        })
        self.hub = self.env['sensor_monitor.hub'].create({
            'name': 'Hub', 'site_id': site.id, 'hub_code': 'HUB-040',
        })
        self.coletor = self.env['sensor_monitor.coletor'].create({
            'name': 'Coletor RS485', 'hub_id': self.hub.id,
            'coletor_code': 'COL-040', 'tipo': 'hub_rs485_embutido',
        })
        self.bus = self.env['sensor_monitor.rs485.bus'].create({
            'hub_id': self.hub.id, 'name': 'Barramento 1', 'bus_code': 'BUS-001',
            'serial_port': '/dev/ttyAMA0', 'baud_rate': 9600,
        })
        self.profile = self.env['sensor_monitor.modbus.profile'].create({
            'name': 'Transmissor Temp/Umidade TX-100', 'fabricante': 'Fabricante X', 'modelo': 'TX-100',
        })
        self.register = self.env['sensor_monitor.modbus.profile.register'].create({
            'profile_id': self.profile.id, 'name': 'Temperatura',
            'measurement_type_id': self.env.ref('afr_sentinela_sensor_monitor.measurement_type_temperatura').id,
            'function_code': '04_input', 'register_address': 0, 'register_count': 1,
            'data_type': 'int16', 'byte_order': 'big', 'scale': 0.1, 'offset': 0.0,
        })

    def test_modbus_device_unique_slave_per_bus(self):
        self.env['sensor_monitor.modbus.device'].create({
            'name': 'Transdutor 1', 'rs485_bus_id': self.bus.id,
            'slave_address': 1, 'profile_id': self.profile.id,
        })
        with self.assertRaises(Exception):
            self.env['sensor_monitor.modbus.device'].create({
                'name': 'Transdutor 2', 'rs485_bus_id': self.bus.id,
                'slave_address': 1, 'profile_id': self.profile.id,
            })

    def test_sensor_modbus_register_requires_rs485(self):
        with self.assertRaises(ValidationError):
            self.env['sensor_monitor.sensor'].create({
                'name': 'Sensor Modbus', 'sensor_code': 'SNR-040',
                'coletor_id': self.coletor.id, 'area_id': self.area.id,
                'measurement_type_id': self.env.ref('afr_sentinela_sensor_monitor.measurement_type_temperatura').id,
                'protocolo_origem': '4-20ma',
                'modbus_register_id': self.register.id,
            })

    def test_sensor_modbus_register_ok_with_rs485(self):
        sensor = self.env['sensor_monitor.sensor'].create({
            'name': 'Sensor Modbus', 'sensor_code': 'SNR-041',
            'coletor_id': self.coletor.id, 'area_id': self.area.id,
            'measurement_type_id': self.env.ref('afr_sentinela_sensor_monitor.measurement_type_temperatura').id,
            'protocolo_origem': 'rs485',
            'modbus_register_id': self.register.id,
        })
        self.assertEqual(sensor.modbus_register_id, self.register)
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `docker compose exec odoo odoo -d sentinela --db_host=db --db_user=odoo --db_password=odoo -u afr_sentinela_sensor_monitor --test-enable --stop-after-init --test-tags /afr_sentinela_sensor_monitor`
Expected: falha, modelo `sensor_monitor.rs485.bus` não encontrado.

- [ ] **Step 3: Implementar `models/rs485_bus.py`**

```python
from odoo import api, fields, models

from .common import validate_code


class Rs485Bus(models.Model):
    _name = 'sensor_monitor.rs485.bus'
    _description = 'Barramento RS-485'

    hub_id = fields.Many2one('sensor_monitor.hub', required=True)
    name = fields.Char(required=True)
    bus_code = fields.Char(required=True)
    serial_port = fields.Char(required=True)
    baud_rate = fields.Integer(default=9600, required=True)
    parity = fields.Selection([
        ('none', 'Nenhuma'), ('even', 'Par'), ('odd', 'Ímpar'),
    ], default='none', required=True)
    stop_bits = fields.Selection([('1', '1'), ('2', '2')], default='1', required=True)
    data_bits = fields.Integer(default=8, required=True)

    _sql_constraints = [
        ('bus_code_unique_per_hub', 'unique(hub_id, bus_code)', 'Código de barramento já usado neste hub.'),
    ]

    @api.constrains('bus_code')
    def _check_bus_code(self):
        for bus in self:
            validate_code(bus.bus_code)
```

- [ ] **Step 4: Implementar `models/modbus_profile.py`**

```python
from odoo import fields, models


class ModbusProfile(models.Model):
    _name = 'sensor_monitor.modbus.profile'
    _description = 'Perfil Modbus (catálogo)'

    name = fields.Char(required=True)
    fabricante = fields.Char()
    modelo = fields.Char()
    register_ids = fields.One2many('sensor_monitor.modbus.profile.register', 'profile_id')


class ModbusProfileRegister(models.Model):
    _name = 'sensor_monitor.modbus.profile.register'
    _description = 'Registrador do Perfil Modbus'

    profile_id = fields.Many2one('sensor_monitor.modbus.profile', required=True)
    name = fields.Char(required=True)
    measurement_type_id = fields.Many2one('sensor_monitor.measurement.type', required=True)
    function_code = fields.Selection([
        ('03_holding', '03 - Holding'), ('04_input', '04 - Input'),
    ], required=True)
    register_address = fields.Integer(required=True)
    register_count = fields.Integer(default=1, required=True)
    data_type = fields.Selection([
        ('int16', 'int16'), ('uint16', 'uint16'),
        ('int32', 'int32'), ('uint32', 'uint32'), ('float32', 'float32'),
    ], required=True)
    byte_order = fields.Selection([
        ('big', 'Big'), ('little', 'Little'),
        ('big_swap', 'Big Swap'), ('little_swap', 'Little Swap'),
    ], default='big', required=True)
    scale = fields.Float(default=1.0)
    offset = fields.Float(default=0.0)
    unidade = fields.Char()
```

- [ ] **Step 5: Implementar `models/modbus_device.py`**

```python
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ModbusDevice(models.Model):
    _name = 'sensor_monitor.modbus.device'
    _description = 'Dispositivo Modbus'

    name = fields.Char(required=True)
    rs485_bus_id = fields.Many2one('sensor_monitor.rs485.bus', required=True)
    slave_address = fields.Integer(required=True)
    profile_id = fields.Many2one('sensor_monitor.modbus.profile', required=True)

    _sql_constraints = [
        ('unique_slave_per_bus', 'unique(rs485_bus_id, slave_address)',
         'Endereço de escravo já usado neste barramento.'),
    ]

    @api.constrains('slave_address')
    def _check_slave_address_range(self):
        for device in self:
            if not 1 <= device.slave_address <= 247:
                raise ValidationError('slave_address deve estar entre 1 e 247.')
```

- [ ] **Step 6: Implementar `models/sensor_rs485_ext.py`**

```python
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SensorRs485Ext(models.Model):
    _inherit = 'sensor_monitor.sensor'

    modbus_register_id = fields.Many2one('sensor_monitor.modbus.profile.register')

    @api.constrains('modbus_register_id', 'protocolo_origem')
    def _check_modbus_register_requires_rs485(self):
        for sensor in self:
            if sensor.modbus_register_id and sensor.protocolo_origem != 'rs485':
                raise ValidationError(
                    'modbus_register_id só pode ser definido quando protocolo_origem = rs485.'
                )
```

- [ ] **Step 7: Atualizar `models/__init__.py`** (adicionar, ao final: `from . import rs485_bus`, `from . import modbus_profile`, `from . import modbus_device`, `from . import sensor_rs485_ext`)

- [ ] **Step 8: Atualizar `tests/__init__.py`** (adicionar `from . import test_rs485_modbus`)

- [ ] **Step 9: Rodar os testes e confirmar que passam**

Run: `docker compose exec odoo odoo -d sentinela --db_host=db --db_user=odoo --db_password=odoo -u afr_sentinela_sensor_monitor --test-enable --stop-after-init --test-tags /afr_sentinela_sensor_monitor`
Expected: todos os testes OK.

- [ ] **Step 10: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor
git commit -m "feat: ramo RS-485/Modbus (bus, profile, device) + extensão do sensor"
```

---

## Task 10: Segurança (grupos, `ir.model.access.csv`, `ir.rule` multi-tenant)

**Files:**
- Create: `addons/afr_sentinela_sensor_monitor/security/security_rules.xml`
- Create: `addons/afr_sentinela_sensor_monitor/security/ir.model.access.csv`
- Modify: `addons/afr_sentinela_sensor_monitor/__manifest__.py`
- Modify: `addons/afr_sentinela_sensor_monitor/tests/__init__.py`
- Test: `addons/afr_sentinela_sensor_monitor/tests/test_security_rules.py`

**Interfaces:**
- Consumes: todos os modelos das Tasks 4–9.
- Produces: grupos `group_sensor_monitor_view`, `group_sensor_monitor_operation`, `group_sensor_monitor_advanced_config`, `group_sensor_monitor_admin`; `ir.rule` filtrando por `partner_id` do cliente em todos os modelos com cadeia até `site_id` (exceto lookups globais).

- [ ] **Step 1: Escrever `tests/test_security_rules.py`**

```python
from odoo.tests.common import TransactionCase


class TestSecurityRules(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner_a = self.env['res.partner'].create({'name': 'Hospital A'})
        self.partner_b = self.env['res.partner'].create({'name': 'Hospital B'})
        self.site_a = self.env['sensor_monitor.site'].create({
            'name': 'CME A', 'partner_id': self.partner_a.id,
            'site_code': 'SITE-A', 'vertical': 'cme_hospitalar',
        })
        self.site_b = self.env['sensor_monitor.site'].create({
            'name': 'CME B', 'partner_id': self.partner_b.id,
            'site_code': 'SITE-B', 'vertical': 'cme_hospitalar',
        })
        view_group = self.env.ref('afr_sentinela_sensor_monitor.group_sensor_monitor_view')
        self.user_a = self.env['res.users'].create({
            'name': 'Usuário A', 'login': 'usuario_a@teste.com',
            'partner_id': self.partner_a.id,
            'groups_id': [(6, 0, [view_group.id, self.env.ref('base.group_user').id])],
        })

    def test_user_sees_only_own_partner_site(self):
        sites = self.env['sensor_monitor.site'].with_user(self.user_a).search([])
        self.assertIn(self.site_a, sites)
        self.assertNotIn(self.site_b, sites)

    def test_admin_group_sees_all_sites(self):
        admin_group = self.env.ref('afr_sentinela_sensor_monitor.group_sensor_monitor_admin')
        admin_user = self.env['res.users'].create({
            'name': 'Admin Interno', 'login': 'admin_interno@teste.com',
            'groups_id': [(6, 0, [admin_group.id, self.env.ref('base.group_user').id])],
        })
        sites = self.env['sensor_monitor.site'].with_user(admin_user).search([])
        self.assertIn(self.site_a, sites)
        self.assertIn(self.site_b, sites)
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `docker compose exec odoo odoo -d sentinela --db_host=db --db_user=odoo --db_password=odoo -u afr_sentinela_sensor_monitor --test-enable --stop-after-init --test-tags /afr_sentinela_sensor_monitor`
Expected: falha, `group_sensor_monitor_view` não encontrado (external id inexistente).

- [ ] **Step 3: Criar `security/security_rules.xml`**

```xml
<odoo>
    <record id="group_sensor_monitor_view" model="res.groups">
        <field name="name">Sensor Monitor / Visualização</field>
    </record>
    <record id="group_sensor_monitor_operation" model="res.groups">
        <field name="name">Sensor Monitor / Operação</field>
    </record>
    <record id="group_sensor_monitor_advanced_config" model="res.groups">
        <field name="name">Sensor Monitor / Configuração Avançada</field>
    </record>
    <record id="group_sensor_monitor_admin" model="res.groups">
        <field name="name">Sensor Monitor / Admin (interno SaaS)</field>
    </record>

    <record id="rule_site_tenant" model="ir.rule">
        <field name="name">Site: isolamento por cliente</field>
        <field name="model_id" ref="model_sensor_monitor_site"/>
        <field name="domain_force">[('partner_id', '=', user.partner_id.commercial_partner_id.id)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_view')), (4, ref('group_sensor_monitor_operation')), (4, ref('group_sensor_monitor_advanced_config'))]"/>
    </record>
    <record id="rule_site_admin" model="ir.rule">
        <field name="name">Site: admin vê tudo</field>
        <field name="model_id" ref="model_sensor_monitor_site"/>
        <field name="domain_force">[(1, '=', 1)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_admin'))]"/>
    </record>

    <record id="rule_area_tenant" model="ir.rule">
        <field name="name">Área: isolamento por cliente</field>
        <field name="model_id" ref="model_sensor_monitor_area"/>
        <field name="domain_force">[('site_id.partner_id', '=', user.partner_id.commercial_partner_id.id)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_view')), (4, ref('group_sensor_monitor_operation')), (4, ref('group_sensor_monitor_advanced_config'))]"/>
    </record>
    <record id="rule_area_admin" model="ir.rule">
        <field name="name">Área: admin vê tudo</field>
        <field name="model_id" ref="model_sensor_monitor_area"/>
        <field name="domain_force">[(1, '=', 1)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_admin'))]"/>
    </record>

    <record id="rule_hub_tenant" model="ir.rule">
        <field name="name">Hub: isolamento por cliente</field>
        <field name="model_id" ref="model_sensor_monitor_hub"/>
        <field name="domain_force">[('site_id.partner_id', '=', user.partner_id.commercial_partner_id.id)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_view')), (4, ref('group_sensor_monitor_operation')), (4, ref('group_sensor_monitor_advanced_config'))]"/>
    </record>
    <record id="rule_hub_admin" model="ir.rule">
        <field name="name">Hub: admin vê tudo</field>
        <field name="model_id" ref="model_sensor_monitor_hub"/>
        <field name="domain_force">[(1, '=', 1)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_admin'))]"/>
    </record>

    <record id="rule_coletor_tenant" model="ir.rule">
        <field name="name">Coletor: isolamento por cliente</field>
        <field name="model_id" ref="model_sensor_monitor_coletor"/>
        <field name="domain_force">[('hub_id.site_id.partner_id', '=', user.partner_id.commercial_partner_id.id)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_view')), (4, ref('group_sensor_monitor_operation')), (4, ref('group_sensor_monitor_advanced_config'))]"/>
    </record>
    <record id="rule_coletor_admin" model="ir.rule">
        <field name="name">Coletor: admin vê tudo</field>
        <field name="model_id" ref="model_sensor_monitor_coletor"/>
        <field name="domain_force">[(1, '=', 1)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_admin'))]"/>
    </record>

    <record id="rule_sensor_tenant" model="ir.rule">
        <field name="name">Sensor: isolamento por cliente</field>
        <field name="model_id" ref="model_sensor_monitor_sensor"/>
        <field name="domain_force">[('coletor_id.hub_id.site_id.partner_id', '=', user.partner_id.commercial_partner_id.id)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_view')), (4, ref('group_sensor_monitor_operation')), (4, ref('group_sensor_monitor_advanced_config'))]"/>
    </record>
    <record id="rule_sensor_admin" model="ir.rule">
        <field name="name">Sensor: admin vê tudo</field>
        <field name="model_id" ref="model_sensor_monitor_sensor"/>
        <field name="domain_force">[(1, '=', 1)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_admin'))]"/>
    </record>

    <record id="rule_alarm_threshold_tenant" model="ir.rule">
        <field name="name">Threshold: isolamento por cliente</field>
        <field name="model_id" ref="model_sensor_monitor_alarm_threshold"/>
        <field name="domain_force">[('sensor_id.coletor_id.hub_id.site_id.partner_id', '=', user.partner_id.commercial_partner_id.id)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_view')), (4, ref('group_sensor_monitor_operation')), (4, ref('group_sensor_monitor_advanced_config'))]"/>
    </record>
    <record id="rule_alarm_threshold_admin" model="ir.rule">
        <field name="name">Threshold: admin vê tudo</field>
        <field name="model_id" ref="model_sensor_monitor_alarm_threshold"/>
        <field name="domain_force">[(1, '=', 1)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_admin'))]"/>
    </record>

    <record id="rule_alarm_event_tenant" model="ir.rule">
        <field name="name">Evento de alarme: isolamento por cliente</field>
        <field name="model_id" ref="model_sensor_monitor_alarm_event"/>
        <field name="domain_force">[('coletor_id.hub_id.site_id.partner_id', '=', user.partner_id.commercial_partner_id.id)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_view')), (4, ref('group_sensor_monitor_operation')), (4, ref('group_sensor_monitor_advanced_config'))]"/>
    </record>
    <record id="rule_alarm_event_admin" model="ir.rule">
        <field name="name">Evento de alarme: admin vê tudo</field>
        <field name="model_id" ref="model_sensor_monitor_alarm_event"/>
        <field name="domain_force">[(1, '=', 1)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_admin'))]"/>
    </record>

    <record id="rule_file_ledger_tenant" model="ir.rule">
        <field name="name">Ledger: isolamento por cliente</field>
        <field name="model_id" ref="model_sensor_monitor_file_ledger"/>
        <field name="domain_force">[('coletor_id.hub_id.site_id.partner_id', '=', user.partner_id.commercial_partner_id.id)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_view')), (4, ref('group_sensor_monitor_operation')), (4, ref('group_sensor_monitor_advanced_config'))]"/>
    </record>
    <record id="rule_file_ledger_admin" model="ir.rule">
        <field name="name">Ledger: admin vê tudo</field>
        <field name="model_id" ref="model_sensor_monitor_file_ledger"/>
        <field name="domain_force">[(1, '=', 1)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_admin'))]"/>
    </record>

    <record id="rule_rs485_bus_tenant" model="ir.rule">
        <field name="name">Barramento RS-485: isolamento por cliente</field>
        <field name="model_id" ref="model_sensor_monitor_rs485_bus"/>
        <field name="domain_force">[('hub_id.site_id.partner_id', '=', user.partner_id.commercial_partner_id.id)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_view')), (4, ref('group_sensor_monitor_operation')), (4, ref('group_sensor_monitor_advanced_config'))]"/>
    </record>
    <record id="rule_rs485_bus_admin" model="ir.rule">
        <field name="name">Barramento RS-485: admin vê tudo</field>
        <field name="model_id" ref="model_sensor_monitor_rs485_bus"/>
        <field name="domain_force">[(1, '=', 1)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_admin'))]"/>
    </record>

    <record id="rule_modbus_device_tenant" model="ir.rule">
        <field name="name">Dispositivo Modbus: isolamento por cliente</field>
        <field name="model_id" ref="model_sensor_monitor_modbus_device"/>
        <field name="domain_force">[('rs485_bus_id.hub_id.site_id.partner_id', '=', user.partner_id.commercial_partner_id.id)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_view')), (4, ref('group_sensor_monitor_operation')), (4, ref('group_sensor_monitor_advanced_config'))]"/>
    </record>
    <record id="rule_modbus_device_admin" model="ir.rule">
        <field name="name">Dispositivo Modbus: admin vê tudo</field>
        <field name="model_id" ref="model_sensor_monitor_modbus_device"/>
        <field name="domain_force">[(1, '=', 1)]</field>
        <field name="groups" eval="[(4, ref('group_sensor_monitor_admin'))]"/>
    </record>
</odoo>
```

- [ ] **Step 4: Criar `security/ir.model.access.csv`**

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_area_category_view,area.category.view,model_sensor_monitor_area_category,group_sensor_monitor_view,1,0,0,0
access_area_category_admin,area.category.admin,model_sensor_monitor_area_category,group_sensor_monitor_admin,1,1,1,1
access_measurement_type_view,measurement.type.view,model_sensor_monitor_measurement_type,group_sensor_monitor_view,1,0,0,0
access_measurement_type_admin,measurement.type.admin,model_sensor_monitor_measurement_type,group_sensor_monitor_admin,1,1,1,1
access_site_view,site.view,model_sensor_monitor_site,group_sensor_monitor_view,1,0,0,0
access_site_admin,site.admin,model_sensor_monitor_site,group_sensor_monitor_admin,1,1,1,1
access_area_view,area.view,model_sensor_monitor_area,group_sensor_monitor_view,1,0,0,0
access_area_admin,area.admin,model_sensor_monitor_area,group_sensor_monitor_admin,1,1,1,1
access_hub_view,hub.view,model_sensor_monitor_hub,group_sensor_monitor_view,1,0,0,0
access_hub_admin,hub.admin,model_sensor_monitor_hub,group_sensor_monitor_admin,1,1,1,1
access_coletor_view,coletor.view,model_sensor_monitor_coletor,group_sensor_monitor_view,1,0,0,0
access_coletor_admin,coletor.admin,model_sensor_monitor_coletor,group_sensor_monitor_admin,1,1,1,1
access_sensor_view,sensor.view,model_sensor_monitor_sensor,group_sensor_monitor_view,1,0,0,0
access_sensor_admin,sensor.admin,model_sensor_monitor_sensor,group_sensor_monitor_admin,1,1,1,1
access_alarm_threshold_view,alarm.threshold.view,model_sensor_monitor_alarm_threshold,group_sensor_monitor_view,1,0,0,0
access_alarm_threshold_advanced,alarm.threshold.advanced,model_sensor_monitor_alarm_threshold,group_sensor_monitor_advanced_config,1,1,1,0
access_alarm_threshold_admin,alarm.threshold.admin,model_sensor_monitor_alarm_threshold,group_sensor_monitor_admin,1,1,1,1
access_alarm_event_view,alarm.event.view,model_sensor_monitor_alarm_event,group_sensor_monitor_view,1,0,0,0
access_alarm_event_operation,alarm.event.operation,model_sensor_monitor_alarm_event,group_sensor_monitor_operation,1,1,1,0
access_alarm_event_admin,alarm.event.admin,model_sensor_monitor_alarm_event,group_sensor_monitor_admin,1,1,1,1
access_file_ledger_view,file.ledger.view,model_sensor_monitor_file_ledger,group_sensor_monitor_view,1,0,0,0
access_file_ledger_admin,file.ledger.admin,model_sensor_monitor_file_ledger,group_sensor_monitor_admin,1,1,1,1
access_rs485_bus_view,rs485.bus.view,model_sensor_monitor_rs485_bus,group_sensor_monitor_view,1,0,0,0
access_rs485_bus_admin,rs485.bus.admin,model_sensor_monitor_rs485_bus,group_sensor_monitor_admin,1,1,1,1
access_modbus_profile_view,modbus.profile.view,model_sensor_monitor_modbus_profile,group_sensor_monitor_view,1,0,0,0
access_modbus_profile_admin,modbus.profile.admin,model_sensor_monitor_modbus_profile,group_sensor_monitor_admin,1,1,1,1
access_modbus_profile_register_view,modbus.profile.register.view,model_sensor_monitor_modbus_profile_register,group_sensor_monitor_view,1,0,0,0
access_modbus_profile_register_admin,modbus.profile.register.admin,model_sensor_monitor_modbus_profile_register,group_sensor_monitor_admin,1,1,1,1
access_modbus_device_view,modbus.device.view,model_sensor_monitor_modbus_device,group_sensor_monitor_view,1,0,0,0
access_modbus_device_admin,modbus.device.admin,model_sensor_monitor_modbus_device,group_sensor_monitor_admin,1,1,1,1
```

- [ ] **Step 5: Atualizar `__manifest__.py`**

```python
    'data': [
        'security/security_rules.xml',
        'security/ir.model.access.csv',
        'data/area_category_data.xml',
        'data/measurement_type_data.xml',
        'data/file_ledger_cron_data.xml',
    ],
```

- [ ] **Step 6: Atualizar `tests/__init__.py`** (adicionar `from . import test_security_rules`)

- [ ] **Step 7: Rodar os testes e confirmar que passam**

Run: `docker compose exec odoo odoo -d sentinela --db_host=db --db_user=odoo --db_password=odoo -u afr_sentinela_sensor_monitor --test-enable --stop-after-init --test-tags /afr_sentinela_sensor_monitor`
Expected: todos os testes OK.

- [ ] **Step 8: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor
git commit -m "feat: grupos de acesso e ir.rule multi-tenant"
```

---

## Task 11: Views administrativas + menu

**Files:**
- Create: `addons/afr_sentinela_sensor_monitor/views/site_views.xml`
- Create: `addons/afr_sentinela_sensor_monitor/views/area_views.xml`
- Create: `addons/afr_sentinela_sensor_monitor/views/hub_views.xml`
- Create: `addons/afr_sentinela_sensor_monitor/views/coletor_views.xml`
- Create: `addons/afr_sentinela_sensor_monitor/views/sensor_views.xml`
- Create: `addons/afr_sentinela_sensor_monitor/views/alarm_threshold_views.xml`
- Create: `addons/afr_sentinela_sensor_monitor/views/alarm_event_views.xml`
- Create: `addons/afr_sentinela_sensor_monitor/views/file_ledger_views.xml`
- Create: `addons/afr_sentinela_sensor_monitor/views/rs485_modbus_views.xml`
- Create: `addons/afr_sentinela_sensor_monitor/views/menu.xml`
- Modify: `addons/afr_sentinela_sensor_monitor/__manifest__.py`

**Interfaces:**
- Consumes: todos os modelos das Tasks 4–9, grupos da Task 10.
- Produces: menu "Sensor Monitor" navegável no Odoo, com ações de lista/form para os 14 modelos.

- [ ] **Step 1: Criar `views/site_views.xml`**

```xml
<odoo>
    <record id="view_site_list" model="ir.ui.view">
        <field name="name">sensor_monitor.site.list</field>
        <field name="model">sensor_monitor.site</field>
        <field name="arch" type="xml">
            <list>
                <field name="name"/>
                <field name="partner_id"/>
                <field name="site_code"/>
                <field name="vertical"/>
                <field name="lifecycle_status"/>
            </list>
        </field>
    </record>
    <record id="view_site_form" model="ir.ui.view">
        <field name="name">sensor_monitor.site.form</field>
        <field name="model">sensor_monitor.site</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <group>
                        <field name="name"/>
                        <field name="partner_id"/>
                        <field name="site_code"/>
                        <field name="vertical"/>
                        <field name="ativo"/>
                        <field name="endereco"/>
                        <field name="timezone"/>
                    </group>
                    <group string="Retenção e ciclo de vida">
                        <field name="retention_mode"/>
                        <field name="retention_years"/>
                        <field name="lifecycle_status"/>
                        <field name="offboarding_data"/>
                        <field name="export_entregue_em"/>
                    </group>
                </sheet>
            </form>
        </field>
    </record>
    <record id="action_site" model="ir.actions.act_window">
        <field name="name">Sites</field>
        <field name="res_model">sensor_monitor.site</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

- [ ] **Step 2: Criar `views/area_views.xml`**

```xml
<odoo>
    <record id="view_area_list" model="ir.ui.view">
        <field name="name">sensor_monitor.area.list</field>
        <field name="model">sensor_monitor.area</field>
        <field name="arch" type="xml">
            <list>
                <field name="name"/>
                <field name="site_id"/>
                <field name="area_category_id"/>
                <field name="area_code"/>
            </list>
        </field>
    </record>
    <record id="view_area_form" model="ir.ui.view">
        <field name="name">sensor_monitor.area.form</field>
        <field name="model">sensor_monitor.area</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <group>
                        <field name="name"/>
                        <field name="site_id"/>
                        <field name="area_category_id"/>
                        <field name="area_code"/>
                    </group>
                </sheet>
            </form>
        </field>
    </record>
    <record id="action_area" model="ir.actions.act_window">
        <field name="name">Áreas</field>
        <field name="res_model">sensor_monitor.area</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

- [ ] **Step 3: Criar `views/hub_views.xml`**

```xml
<odoo>
    <record id="view_hub_list" model="ir.ui.view">
        <field name="name">sensor_monitor.hub.list</field>
        <field name="model">sensor_monitor.hub</field>
        <field name="arch" type="xml">
            <list>
                <field name="name"/>
                <field name="site_id"/>
                <field name="hub_code"/>
                <field name="status"/>
                <field name="ultimo_contato"/>
            </list>
        </field>
    </record>
    <record id="view_hub_form" model="ir.ui.view">
        <field name="name">sensor_monitor.hub.form</field>
        <field name="model">sensor_monitor.hub</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <group>
                        <field name="name"/>
                        <field name="site_id"/>
                        <field name="hub_code"/>
                        <field name="modelo_hardware"/>
                        <field name="status"/>
                        <field name="firmware_version"/>
                        <field name="ultimo_contato"/>
                    </group>
                    <group string="Segurança">
                        <field name="openvpn_cert_fingerprint"/>
                        <field name="possui_secure_element"/>
                        <field name="secure_element_pubkey_fingerprint"/>
                    </group>
                </sheet>
            </form>
        </field>
    </record>
    <record id="action_hub" model="ir.actions.act_window">
        <field name="name">Hubs</field>
        <field name="res_model">sensor_monitor.hub</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

- [ ] **Step 4: Criar `views/coletor_views.xml`**

```xml
<odoo>
    <record id="view_coletor_list" model="ir.ui.view">
        <field name="name">sensor_monitor.coletor.list</field>
        <field name="model">sensor_monitor.coletor</field>
        <field name="arch" type="xml">
            <list>
                <field name="name"/>
                <field name="hub_id"/>
                <field name="coletor_code"/>
                <field name="tipo"/>
                <field name="status"/>
            </list>
        </field>
    </record>
    <record id="view_coletor_form" model="ir.ui.view">
        <field name="name">sensor_monitor.coletor.form</field>
        <field name="model">sensor_monitor.coletor</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <group>
                        <field name="name"/>
                        <field name="hub_id"/>
                        <field name="coletor_code"/>
                        <field name="tipo"/>
                        <field name="is_hub_embutido" readonly="1"/>
                        <field name="hardware_modelo"/>
                        <field name="status"/>
                        <field name="firmware_version"/>
                    </group>
                </sheet>
            </form>
        </field>
    </record>
    <record id="action_coletor" model="ir.actions.act_window">
        <field name="name">Coletores</field>
        <field name="res_model">sensor_monitor.coletor</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

- [ ] **Step 5: Criar `views/sensor_views.xml`**

```xml
<odoo>
    <record id="view_sensor_list" model="ir.ui.view">
        <field name="name">sensor_monitor.sensor.list</field>
        <field name="model">sensor_monitor.sensor</field>
        <field name="arch" type="xml">
            <list>
                <field name="name"/>
                <field name="sensor_code"/>
                <field name="coletor_id"/>
                <field name="area_id"/>
                <field name="measurement_type_id"/>
                <field name="ativo"/>
            </list>
        </field>
    </record>
    <record id="view_sensor_form" model="ir.ui.view">
        <field name="name">sensor_monitor.sensor.form</field>
        <field name="model">sensor_monitor.sensor</field>
        <field name="arch" type="xml">
            <form>
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
                        <field name="modbus_register_id" invisible="protocolo_origem != 'rs485'"/>
                    </group>
                </sheet>
            </form>
        </field>
    </record>
    <record id="action_sensor" model="ir.actions.act_window">
        <field name="name">Sensores</field>
        <field name="res_model">sensor_monitor.sensor</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

- [ ] **Step 6: Criar `views/alarm_threshold_views.xml`**

```xml
<odoo>
    <record id="view_alarm_threshold_list" model="ir.ui.view">
        <field name="name">sensor_monitor.alarm.threshold.list</field>
        <field name="model">sensor_monitor.alarm.threshold</field>
        <field name="arch" type="xml">
            <list>
                <field name="sensor_id"/>
                <field name="limite_min"/>
                <field name="limite_max"/>
                <field name="is_valor_padrao_regulatorio"/>
            </list>
        </field>
    </record>
    <record id="view_alarm_threshold_form" model="ir.ui.view">
        <field name="name">sensor_monitor.alarm.threshold.form</field>
        <field name="model">sensor_monitor.alarm.threshold</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <group>
                        <field name="sensor_id"/>
                        <field name="limite_min"/>
                        <field name="limite_max"/>
                        <field name="is_valor_padrao_regulatorio"/>
                        <field name="origem_ultima_alteracao"/>
                        <field name="justificativa_desvio"/>
                    </group>
                </sheet>
                <chatter/>
            </form>
        </field>
    </record>
    <record id="action_alarm_threshold" model="ir.actions.act_window">
        <field name="name">Limiares de Alarme</field>
        <field name="res_model">sensor_monitor.alarm.threshold</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

- [ ] **Step 7: Criar `views/alarm_event_views.xml`**

```xml
<odoo>
    <record id="view_alarm_event_list" model="ir.ui.view">
        <field name="name">sensor_monitor.alarm.event.list</field>
        <field name="model">sensor_monitor.alarm.event</field>
        <field name="arch" type="xml">
            <list>
                <field name="sensor_id"/>
                <field name="timestamp_deteccao"/>
                <field name="tipo_violacao"/>
                <field name="status"/>
            </list>
        </field>
    </record>
    <record id="view_alarm_event_form" model="ir.ui.view">
        <field name="name">sensor_monitor.alarm.event.form</field>
        <field name="model">sensor_monitor.alarm.event</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <group>
                        <field name="sensor_id"/>
                        <field name="area_id"/>
                        <field name="coletor_id"/>
                        <field name="timestamp_deteccao"/>
                        <field name="timestamp_resolucao_sensor"/>
                        <field name="valor_lido"/>
                        <field name="tipo_violacao"/>
                        <field name="limite_configurado_snapshot"/>
                        <field name="status"/>
                        <field name="usuario_responsavel_id"/>
                        <field name="data_resolucao"/>
                        <field name="observacoes"/>
                    </group>
                </sheet>
                <chatter/>
            </form>
        </field>
    </record>
    <record id="action_alarm_event" model="ir.actions.act_window">
        <field name="name">Eventos de Alarme</field>
        <field name="res_model">sensor_monitor.alarm.event</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

- [ ] **Step 8: Criar `views/file_ledger_views.xml`**

```xml
<odoo>
    <record id="view_file_ledger_list" model="ir.ui.view">
        <field name="name">sensor_monitor.file.ledger.list</field>
        <field name="model">sensor_monitor.file.ledger</field>
        <field name="arch" type="xml">
            <list>
                <field name="coletor_id"/>
                <field name="hub_id"/>
                <field name="tipo_arquivo"/>
                <field name="data_referencia"/>
                <field name="status_validacao"/>
            </list>
        </field>
    </record>
    <record id="action_file_ledger" model="ir.actions.act_window">
        <field name="name">Ledger de Arquivos</field>
        <field name="res_model">sensor_monitor.file.ledger</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

- [ ] **Step 9: Criar `views/rs485_modbus_views.xml`**

```xml
<odoo>
    <record id="view_rs485_bus_list" model="ir.ui.view">
        <field name="name">sensor_monitor.rs485.bus.list</field>
        <field name="model">sensor_monitor.rs485.bus</field>
        <field name="arch" type="xml">
            <list>
                <field name="name"/>
                <field name="hub_id"/>
                <field name="bus_code"/>
                <field name="serial_port"/>
                <field name="baud_rate"/>
            </list>
        </field>
    </record>
    <record id="action_rs485_bus" model="ir.actions.act_window">
        <field name="name">Barramentos RS-485</field>
        <field name="res_model">sensor_monitor.rs485.bus</field>
        <field name="view_mode">list,form</field>
    </record>

    <record id="view_modbus_profile_list" model="ir.ui.view">
        <field name="name">sensor_monitor.modbus.profile.list</field>
        <field name="model">sensor_monitor.modbus.profile</field>
        <field name="arch" type="xml">
            <list>
                <field name="name"/>
                <field name="fabricante"/>
                <field name="modelo"/>
            </list>
        </field>
    </record>
    <record id="view_modbus_profile_form" model="ir.ui.view">
        <field name="name">sensor_monitor.modbus.profile.form</field>
        <field name="model">sensor_monitor.modbus.profile</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <group>
                        <field name="name"/>
                        <field name="fabricante"/>
                        <field name="modelo"/>
                    </group>
                    <field name="register_ids">
                        <list editable="bottom">
                            <field name="name"/>
                            <field name="measurement_type_id"/>
                            <field name="function_code"/>
                            <field name="register_address"/>
                            <field name="data_type"/>
                            <field name="byte_order"/>
                            <field name="scale"/>
                        </list>
                    </field>
                </sheet>
            </form>
        </field>
    </record>
    <record id="action_modbus_profile" model="ir.actions.act_window">
        <field name="name">Perfis Modbus</field>
        <field name="res_model">sensor_monitor.modbus.profile</field>
        <field name="view_mode">list,form</field>
    </record>

    <record id="view_modbus_device_list" model="ir.ui.view">
        <field name="name">sensor_monitor.modbus.device.list</field>
        <field name="model">sensor_monitor.modbus.device</field>
        <field name="arch" type="xml">
            <list>
                <field name="name"/>
                <field name="rs485_bus_id"/>
                <field name="slave_address"/>
                <field name="profile_id"/>
            </list>
        </field>
    </record>
    <record id="action_modbus_device" model="ir.actions.act_window">
        <field name="name">Dispositivos Modbus</field>
        <field name="res_model">sensor_monitor.modbus.device</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

- [ ] **Step 10: Criar `views/menu.xml`**

```xml
<odoo>
    <menuitem id="menu_sensor_monitor_root" name="Sensor Monitor"/>
    <menuitem id="menu_sensor_monitor_cadastro" name="Cadastro" parent="menu_sensor_monitor_root" sequence="10"/>
    <menuitem id="menu_site" name="Sites" parent="menu_sensor_monitor_cadastro" action="action_site" sequence="10"/>
    <menuitem id="menu_area" name="Áreas" parent="menu_sensor_monitor_cadastro" action="action_area" sequence="20"/>
    <menuitem id="menu_hub" name="Hubs" parent="menu_sensor_monitor_cadastro" action="action_hub" sequence="30"/>
    <menuitem id="menu_coletor" name="Coletores" parent="menu_sensor_monitor_cadastro" action="action_coletor" sequence="40"/>
    <menuitem id="menu_sensor" name="Sensores" parent="menu_sensor_monitor_cadastro" action="action_sensor" sequence="50"/>

    <menuitem id="menu_sensor_monitor_alarmes" name="Alarmes" parent="menu_sensor_monitor_root" sequence="20"/>
    <menuitem id="menu_alarm_threshold" name="Limiares" parent="menu_sensor_monitor_alarmes" action="action_alarm_threshold" sequence="10"/>
    <menuitem id="menu_alarm_event" name="Eventos" parent="menu_sensor_monitor_alarmes" action="action_alarm_event" sequence="20"/>

    <menuitem id="menu_sensor_monitor_rs485" name="RS-485/Modbus" parent="menu_sensor_monitor_root" sequence="30"/>
    <menuitem id="menu_rs485_bus" name="Barramentos" parent="menu_sensor_monitor_rs485" action="action_rs485_bus" sequence="10"/>
    <menuitem id="menu_modbus_profile" name="Perfis" parent="menu_sensor_monitor_rs485" action="action_modbus_profile" sequence="20"/>
    <menuitem id="menu_modbus_device" name="Dispositivos" parent="menu_sensor_monitor_rs485" action="action_modbus_device" sequence="30"/>

    <menuitem id="menu_sensor_monitor_operacao" name="Operação" parent="menu_sensor_monitor_root" sequence="40"/>
    <menuitem id="menu_file_ledger" name="Ledger de Arquivos" parent="menu_sensor_monitor_operacao" action="action_file_ledger" sequence="10"/>
</odoo>
```

- [ ] **Step 11: Atualizar `__manifest__.py`**

```python
    'data': [
        'security/security_rules.xml',
        'security/ir.model.access.csv',
        'data/area_category_data.xml',
        'data/measurement_type_data.xml',
        'data/file_ledger_cron_data.xml',
        'views/site_views.xml',
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

- [ ] **Step 12: Instalar o módulo e confirmar que sobe sem erro, com o menu presente**

Run: `docker compose exec odoo odoo -d sentinela --db_host=db --db_user=odoo --db_password=odoo -u afr_sentinela_sensor_monitor --stop-after-init`
Expected: sem `CRITICAL`/`ERROR`, exit code 0.

Run: `docker compose exec odoo odoo shell -d sentinela --db_host=db --db_user=odoo --db_password=odoo <<< "print(env.ref('afr_sentinela_sensor_monitor.menu_sensor_monitor_root').name)"`
Expected: imprime `Sensor Monitor`.

- [ ] **Step 13: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor
git commit -m "feat: views administrativas e menu do Sensor Monitor"
```

---

## Task 12: Suíte completa de testes rodando + checagem final do módulo

**Files:**
- Modify: nenhum arquivo novo — task de verificação/fechamento.

**Interfaces:**
- Consumes: tudo das Tasks 1–11.

- [ ] **Step 1: Reinstalar o módulo do zero num banco limpo, com todos os testes habilitados**

Run:
```bash
docker compose exec odoo odoo -d sentinela_ci --db_host=db --db_user=odoo --db_password=odoo -i afr_sentinela_sensor_monitor --test-enable --stop-after-init --test-tags /afr_sentinela_sensor_monitor
```
Expected: instala do zero e todos os testes das Tasks 4–10 passam, sem `FAIL`/`ERROR`/`CRITICAL` no log.

- [ ] **Step 2: Confirmar a hypertable do Timescale ainda íntegra**

Run: `docker compose exec timescaledb psql -U sentinela -d sentinela -c "SELECT hypertable_name, num_dimensions FROM timescaledb_information.hypertables;"`
Expected: `sensor_reading` com `num_dimensions = 2`.

- [ ] **Step 3: Commit final (se houver qualquer ajuste feito durante a verificação)**

```bash
git status
git add -A
git commit -m "chore: verificação final da Fase 1 (módulo Odoo + timescale)" --allow-empty
```
