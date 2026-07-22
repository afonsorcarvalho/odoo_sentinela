# Fase 5 — Config loop (Plano A: servidor) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lado servidor do laço de configuração da Fase 5 — o Odoo publica a config Modbus de um hub (arquivo no SFTP + sinal MQTT retido), rastreia presença do hub, e fecha o drift quando recebe o report de "aplicado". Tudo testável no Docker sem o Hub real.

**Architecture:** Broker Mosquitto novo no stack. A API FastAPI ganha um cliente MQTT (paho), um serializador que lê a árvore Modbus do Odoo e produz o `config.yaml` operacional, um escritor SFTP (paramiko → SFTPGo), uma rota interna de publicação, um rastreador de presença e um subscriber de report que grava a versão aplicada de volta no Odoo. O Odoo ganha um botão "Publicar configuração" e campos de drift. Segue os padrões existentes (`live_listener` como task de startup; `odoo_cliente.executar` para XML-RPC).

**Tech Stack:** FastAPI, paho-mqtt, paramiko, Mosquitto (eclipse-mosquitto), Odoo 18 (addon `afr_sentinela_sensor_monitor`), pytest, PyYAML.

## Global Constraints

- Contrato do arquivo de config = subconjunto **operacional** do `config.yaml` do Hub (`hub/config.py`): `version, intervalo_leitura_s, barramentos[].{porta,baud,paridade,stop_bits,dispositivos[].{endereco,driver,canais[].{ch,sensor_id,area_id,tipo_medida,unidade,protocolo_origem,map:{in,out},filtro}}}`. **Nunca** inclui identidade/creds (hub_id, coletor_id, chaves, sftp:, mqtt:).
- Fonte da versão = Odoo `sensor_monitor.hub.config_version_desejada` (Integer, já existe). Campos existentes: `config_version_aplicada`, `config_version_reportada_em`, `hub_code`.
- Tópicos MQTT (exatos): `sentinela/status/hub/<code>` (retido+LWT), `sentinela/config/notify/hub/<code>` (retido), `sentinela/config/ack/hub/<code>`, `sentinela/config/applied/hub/<code>`. `<code>` = `hub.hub_code`.
- Sem assinatura de config na v1 (confia no canal). Rota interna da API autenticada por secret compartilhado (env `CONFIG_PUBLISH_SECRET` na API; `ir.config_parameter` `sentinela.config_publish_secret` no Odoo), separado do JWT de usuário.
- Arquivo SFTP: `/config/<hub_code>/config-v<N>.yaml`. Um SFTPGo único (o mesmo do caminho do dado).
- Driver N4AIB16: entrega mA; calibração relevante é `map` mA→engenharia (nível sensor). Campos Odoo novos (§7 da spec): `modbus.profile.driver`; `sensor`: `modbus_channel`, `ma_in_min`, `ma_in_max`, `eng_out_min`, `eng_out_max`, `filtro_tipo`, `filtro_alpha`.
- Rodar pytest a partir da raiz do repo. Stack de teste sobe via `docker compose` (agora inclui `mosquitto`).

---

### Task 1: Broker Mosquitto no stack

**Files:**
- Create: `mosquitto/mosquitto.conf`
- Modify: `docker-compose.yml` (novo serviço `mosquitto`)
- Test: `api/tests/test_mqtt_broker.py`

**Interfaces:**
- Produces: broker MQTT acessível em `localhost:1883` (host) / `mosquitto:1883` (rede Docker). Tópicos livres nesta fatia (auth mínima).

- [ ] **Step 1: Escrever o teste de roundtrip do broker**

```python
# api/tests/test_mqtt_broker.py
import json
import os
import time

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))


def test_broker_pub_sub_roundtrip():
    recebidas = []
    sub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='test-sub')
    sub.on_message = lambda c, u, m: recebidas.append((m.topic, m.payload))
    sub.connect(MQTT_HOST, MQTT_PORT, 30)
    sub.subscribe('sentinela/teste/#', qos=1)
    sub.loop_start()
    time.sleep(0.5)

    pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='test-pub')
    pub.connect(MQTT_HOST, MQTT_PORT, 30)
    pub.publish('sentinela/teste/x', json.dumps({'ok': 1}), qos=1, retain=False)
    pub.disconnect()

    for _ in range(40):
        if recebidas:
            break
        time.sleep(0.1)
    sub.loop_stop()
    assert any(t == 'sentinela/teste/x' for t, _ in recebidas)
```

- [ ] **Step 2: Rodar o teste e confirmar que falha (sem broker)**

Run: `python -m pytest api/tests/test_mqtt_broker.py -q`
Expected: FAIL (ConnectionRefusedError — não há broker em 1883).

- [ ] **Step 3: Criar a config do Mosquitto**

```conf
# mosquitto/mosquitto.conf
listener 1883
allow_anonymous true
persistence true
persistence_location /mosquitto/data/
```

- [ ] **Step 4: Adicionar o serviço ao docker-compose.yml**

```yaml
# docker-compose.yml — novo serviço (ao lado de db/odoo/timescaledb/sftpgo)
  mosquitto:
    image: eclipse-mosquitto:2
    ports:
      - "1883:1883"          # MQTT (LAN no dev; restringir à VPN em prod)
    volumes:
      - ./mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
      - mosquitto-data:/mosquitto/data
    restart: unless-stopped
```

E adicionar `mosquitto-data:` na seção `volumes:` no fim do arquivo.

- [ ] **Step 5: Subir o broker e rodar o teste**

Run:
```bash
docker compose up -d mosquitto
python -m pytest api/tests/test_mqtt_broker.py -q
```
Expected: PASS. (paho-mqtt já está no `.venv`? Se não: `pip install paho-mqtt` e adicionar a `api/requirements.txt`.)

- [ ] **Step 6: Adicionar paho-mqtt a api/requirements.txt e commitar**

```bash
grep -q paho-mqtt api/requirements.txt || echo 'paho-mqtt>=2.0' >> api/requirements.txt
git add mosquitto/mosquitto.conf docker-compose.yml api/tests/test_mqtt_broker.py api/requirements.txt
git commit -m "feat(fase5): broker Mosquitto no stack + teste de roundtrip"
```

---

### Task 2: Cliente MQTT da API (`api/mqtt.py`)

**Files:**
- Create: `api/mqtt.py`
- Test: `api/tests/test_mqtt_cliente.py`

**Interfaces:**
- Produces:
  - `publicar(topico: str, payload: dict, retain: bool = False) -> None` — conecta, publica QoS1, desconecta (síncrono, para uso na rota de publicação).
  - `class OuvinteMqtt` com `on_mensagem: Callable[[str, dict], None]`, método `iniciar(topicos: list[str])` (loop em thread) e `parar()`. Usado pelo rastreador de presença e pelo subscriber de report.

- [ ] **Step 1: Escrever o teste do publicar retido**

```python
# api/tests/test_mqtt_cliente.py
import json
import os
import time

import paho.mqtt.client as mqtt

from api import mqtt as api_mqtt

MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))


def _ler_retido(topico, timeout=4.0):
    got = []
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='test-retido')
    c.on_message = lambda cl, u, m: got.append(m.payload)
    c.connect(MQTT_HOST, MQTT_PORT, 30)
    c.subscribe(topico, qos=1)
    c.loop_start()
    fim = time.time() + timeout
    while time.time() < fim and not got:
        time.sleep(0.05)
    c.loop_stop()
    return json.loads(got[0]) if got else None


def test_publicar_retido_fica_disponivel_para_novo_assinante():
    topico = 'sentinela/teste/retido'
    api_mqtt.publicar(topico, {'version': 7}, retain=True)
    assert _ler_retido(topico) == {'version': 7}
    # limpeza do retido
    api_mqtt.publicar(topico, {}, retain=True)
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `python -m pytest api/tests/test_mqtt_cliente.py -q`
Expected: FAIL (`ModuleNotFoundError: api.mqtt` ou AttributeError).

- [ ] **Step 3: Implementar `api/mqtt.py`**

```python
# api/mqtt.py
import json
import os

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))
_KEEPALIVE = 30


def publicar(topico, payload, retain=False):
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.connect(MQTT_HOST, MQTT_PORT, _KEEPALIVE)
    c.loop_start()  # sem o loop de rede, wait_for_publish() nunca recebe o PUBACK e estoura 5s
    try:
        info = c.publish(topico, json.dumps(payload), qos=1, retain=retain)
        info.wait_for_publish(timeout=5)
    finally:
        c.loop_stop()
        c.disconnect()


class OuvinteMqtt:
    def __init__(self, on_mensagem):
        self._on = on_mensagem
        self._c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._c.on_message = self._despachar

    def _despachar(self, cliente, userdata, msg):
        try:
            dados = json.loads(msg.payload) if msg.payload else {}
        except json.JSONDecodeError:
            return
        self._on(msg.topic, dados)

    def iniciar(self, topicos):
        self._c.connect(MQTT_HOST, MQTT_PORT, _KEEPALIVE)
        for t in topicos:
            self._c.subscribe(t, qos=1)
        self._c.loop_start()

    def parar(self):
        self._c.loop_stop()
        if self._c.is_connected():
            self._c.disconnect()
```

- [ ] **Step 4: Rodar e confirmar passa**

Run: `python -m pytest api/tests/test_mqtt_cliente.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/mqtt.py api/tests/test_mqtt_cliente.py
git commit -m "feat(fase5): cliente MQTT da API (publicar retido + OuvinteMqtt)"
```

---

### Task 3: Extensão do modelo Odoo (§7 da spec)

**Files:**
- Modify: `addons/afr_sentinela_sensor_monitor/models/modbus_profile.py` (campo `driver`)
- Modify: `addons/afr_sentinela_sensor_monitor/models/sensor_rs485_ext.py` (campos de canal/calibração/filtro)
- Modify: `addons/afr_sentinela_sensor_monitor/views/rs485_modbus_views.py` ou o XML de views correspondente (expor os campos)
- Test: `addons/afr_sentinela_sensor_monitor/tests/test_config_fields.py`

**Interfaces:**
- Produces (campos lidos pelo serializador da Task 4):
  - `sensor_monitor.modbus.profile.driver` (Selection `[('n4aib16','N4AIB16')]`, default `n4aib16`)
  - `sensor_monitor.sensor.modbus_channel` (Integer), `ma_in_min`/`ma_in_max`/`eng_out_min`/`eng_out_max` (Float), `filtro_tipo` (Selection `[('none','Nenhum'),('ewma','EWMA')]`, default `none`), `filtro_alpha` (Float, default 0.3)

- [ ] **Step 1: Escrever o teste do módulo Odoo**

```python
# addons/afr_sentinela_sensor_monitor/tests/test_config_fields.py
from odoo.tests.common import TransactionCase


class TestConfigFields(TransactionCase):
    def test_campos_de_config_do_canal_existem_e_gravam(self):
        Sensor = self.env['sensor_monitor.sensor']
        campos = Sensor.fields_get(
            ['modbus_channel', 'ma_in_min', 'ma_in_max', 'eng_out_min',
             'eng_out_max', 'filtro_tipo', 'filtro_alpha'])
        assert set(campos) == {
            'modbus_channel', 'ma_in_min', 'ma_in_max', 'eng_out_min',
            'eng_out_max', 'filtro_tipo', 'filtro_alpha'}

    def test_driver_no_perfil(self):
        campos = self.env['sensor_monitor.modbus.profile'].fields_get(['driver'])
        assert campos['driver']['type'] == 'selection'
```

- [ ] **Step 2: Rodar e confirmar falha**

Run (a partir do container Odoo; stack de pé):
```bash
docker compose exec -T odoo odoo -d sentinela --test-enable --test-tags /afr_sentinela_sensor_monitor:TestConfigFields --stop-after-init -u afr_sentinela_sensor_monitor 2>&1 | tail -20
```
Expected: FAIL (campos não existem).

- [ ] **Step 3: Adicionar o campo `driver` ao perfil**

```python
# addons/afr_sentinela_sensor_monitor/models/modbus_profile.py — na classe ModbusProfile
    driver = fields.Selection(
        [('n4aib16', 'N4AIB16')], default='n4aib16', required=True,
        help='Driver que o Hub usa para ler este perfil (define a família do dispositivo).')
```

- [ ] **Step 4: Adicionar os campos de canal/calibração/filtro ao sensor**

```python
# addons/afr_sentinela_sensor_monitor/models/sensor_rs485_ext.py — na classe SensorRs485Ext
    modbus_channel = fields.Integer(help='Canal físico no dispositivo (ex.: 1-15 no N4AIB16).')
    ma_in_min = fields.Float(default=4.0, help='Corrente mínima da entrada (mA).')
    ma_in_max = fields.Float(default=20.0, help='Corrente máxima da entrada (mA).')
    eng_out_min = fields.Float(help='Valor de engenharia correspondente a ma_in_min.')
    eng_out_max = fields.Float(help='Valor de engenharia correspondente a ma_in_max.')
    filtro_tipo = fields.Selection(
        [('none', 'Nenhum'), ('ewma', 'EWMA')], default='none', required=True)
    filtro_alpha = fields.Float(default=0.3, help='Alpha do EWMA (0-1).')
```

- [ ] **Step 5: Expor os campos nas views**

Abrir o XML de views RS-485/Modbus (`addons/afr_sentinela_sensor_monitor/views/rs485_modbus_views.py` — inspecionar o nome real do arquivo XML referenciado no manifest) e adicionar os campos ao form do sensor RS-485 e ao form do perfil. Exemplo (form do sensor, dentro do `<group>` de campos RS-485):

```xml
<field name="modbus_channel"/>
<field name="ma_in_min"/>
<field name="ma_in_max"/>
<field name="eng_out_min"/>
<field name="eng_out_max"/>
<field name="filtro_tipo"/>
<field name="filtro_alpha" attrs="{'invisible': [('filtro_tipo','=','none')]}"/>
```

- [ ] **Step 6: Rodar o teste e confirmar passa**

Run:
```bash
docker compose exec -T odoo odoo -d sentinela --test-enable --test-tags /afr_sentinela_sensor_monitor:TestConfigFields --stop-after-init -u afr_sentinela_sensor_monitor 2>&1 | tail -20
```
Expected: `0 failed`.

- [ ] **Step 7: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor/models/modbus_profile.py \
        addons/afr_sentinela_sensor_monitor/models/sensor_rs485_ext.py \
        addons/afr_sentinela_sensor_monitor/views/ \
        addons/afr_sentinela_sensor_monitor/tests/test_config_fields.py
git commit -m "feat(fase5): campos de canal/calibração/driver p/ config do Hub (§7)"
```

---

### Task 4: Serializador Odoo → config.yaml operacional

**Files:**
- Create: `api/config_publisher.py`
- Test: `api/tests/test_config_serializer.py`

**Interfaces:**
- Consumes: `get_cliente_servico()` (de `api.odoo`), `odoo_cliente.executar` (de `ingestao.odoo_cliente`), os campos da Task 3.
- Produces: `serializar_config_hub(cliente, hub_code: str) -> dict` — devolve o dict operacional (Global Constraints). Levanta `ValueError` se o hub não existe.

- [ ] **Step 1: Escrever o teste do serializador (com fixture de provisionamento)**

```python
# api/tests/test_config_serializer.py
from api.config_publisher import serializar_config_hub
from api.odoo import get_cliente_servico
from ingestao import odoo_cliente


def _prov_hub_modbus(cliente):
    """Cria hub + bus + N4AIB16 + 1 sensor mapeado. Idempotente por códigos."""
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)
    partner = ex('res.partner', 'search', [], limit=1)[0]
    site = ex('sensor_monitor.site', 'search', [('site_code', '=', 'SITE-CFG-01')]) or [
        ex('sensor_monitor.site', 'create', {
            'name': 'Site Cfg', 'partner_id': partner, 'site_code': 'SITE-CFG-01',
            'vertical': 'cme_hospitalar'})]
    site_id = site[0]
    hub = ex('sensor_monitor.hub', 'search', [('hub_code', '=', 'HUB-CFG-01')]) or [
        ex('sensor_monitor.hub', 'create', {
            'name': 'Hub Cfg', 'site_id': site_id, 'hub_code': 'HUB-CFG-01'})]
    hub_id = hub[0]
    bus = ex('sensor_monitor.rs485.bus', 'search', [('bus_code', '=', 'BUS-CFG-0')]) or [
        ex('sensor_monitor.rs485.bus', 'create', {
            'hub_id': hub_id, 'name': 'Bus0', 'bus_code': 'BUS-CFG-0',
            'serial_port': '/dev/ttyUSB0', 'baud_rate': 9600, 'parity': 'N',
            'stop_bits': '1', 'data_bits': 8})]
    prof = ex('sensor_monitor.modbus.profile', 'search', [('name', '=', 'N4AIB16 Cfg')]) or [
        ex('sensor_monitor.modbus.profile', 'create', {'name': 'N4AIB16 Cfg', 'driver': 'n4aib16'})]
    reg = ex('sensor_monitor.modbus.profile.register', 'search', [('name', '=', 'CH1 Cfg')]) or [
        ex('sensor_monitor.modbus.profile.register', 'create', {
            'profile_id': prof[0], 'name': 'CH1 Cfg',
            'measurement_type_id': ex('sensor_monitor.measurement.type', 'search',
                                      [('code', '=', 'temperatura')])[0],
            'function_code': '04_input', 'register_address': 1, 'register_count': 1,
            'data_type': 'int16'})]
    ex('sensor_monitor.modbus.device', 'search', [('rs485_bus_id', '=', bus[0]),
                                                  ('slave_address', '=', 1)]) or \
        ex('sensor_monitor.modbus.device', 'create', {
            'name': 'N4 Cfg', 'rs485_bus_id': bus[0], 'slave_address': 1, 'profile_id': prof[0]})
    # sensor mapeado ao registrador, com calibração e canal
    sensor = ex('sensor_monitor.sensor', 'search', [('sensor_code', '=', 'SNR-CFG-TEMP-01')])
    vals = {'modbus_register_id': reg[0], 'modbus_channel': 1, 'ma_in_min': 4.0,
            'ma_in_max': 20.0, 'eng_out_min': -50.0, 'eng_out_max': 150.0,
            'filtro_tipo': 'ewma', 'filtro_alpha': 0.3, 'protocolo_origem': 'rs485'}
    if not sensor:
        # criar via a área/coletor conforme o modelo exige — usar provisionar_demo como base
        pass  # detalhe: reusar provisionar_demo p/ ter área/coletor, então write vals
    return 'HUB-CFG-01'


def test_serializar_hub_produz_yaml_operacional():
    cliente = get_cliente_servico()
    hub_code = _prov_hub_modbus(cliente)
    cfg = serializar_config_hub(cliente, hub_code)
    assert cfg['version'] >= 1
    assert 'hub_id' not in cfg and 'sftp' not in cfg  # sem identidade/creds
    bus = cfg['barramentos'][0]
    assert bus['porta'] == '/dev/ttyUSB0' and bus['baud'] == 9600
    disp = bus['dispositivos'][0]
    assert disp['endereco'] == 1 and disp['driver'] == 'n4aib16'
    canal = disp['canais'][0]
    assert canal['ch'] == 1 and canal['map'] == {'in': [4.0, 20.0], 'out': [-50.0, 150.0]}
    assert canal['filtro'] == {'tipo': 'ewma', 'alpha': 0.3}
```

> Nota p/ o implementador: o provisionamento do fixture precisa de área/coletor válidos (o modelo `sensor` exige). Reuse `ingestao.provisionar_demo.provisionar(cliente)` para ter a base e então faça `write` dos campos de config no sensor `SNR-EXP-TEMP-01` (já criado pelo demo), em vez de criar um sensor do zero. Ajuste `hub_code`/códigos conforme o que `provisionar_demo` cria.

- [ ] **Step 2: Rodar e confirmar falha**

Run: `python -m pytest api/tests/test_config_serializer.py -q`
Expected: FAIL (`ModuleNotFoundError: api.config_publisher`).

- [ ] **Step 3: Implementar `serializar_config_hub`**

```python
# api/config_publisher.py
from ingestao import odoo_cliente


def serializar_config_hub(cliente, hub_code):
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)
    hubs = ex('sensor_monitor.hub', 'search_read', [('hub_code', '=', hub_code)],
              fields=['id', 'config_version_desejada'])
    if not hubs:
        raise ValueError(f"hub '{hub_code}' não encontrado")
    hub = hubs[0]

    buses = ex('sensor_monitor.rs485.bus', 'search_read', [('hub_id', '=', hub['id'])],
               fields=['id', 'serial_port', 'baud_rate', 'parity', 'stop_bits'])
    barramentos = []
    for bus in buses:
        devices = ex('sensor_monitor.modbus.device', 'search_read',
                     [('rs485_bus_id', '=', bus['id'])],
                     fields=['id', 'slave_address', 'profile_id'])
        dispositivos = []
        for dev in devices:
            driver = ex('sensor_monitor.modbus.profile', 'read', [dev['profile_id'][0]],
                        fields=['driver'])[0]['driver']
            regs = ex('sensor_monitor.modbus.profile.register', 'search',
                      [('profile_id', '=', dev['profile_id'][0])])
            sensores = ex('sensor_monitor.sensor', 'search_read',
                          [('modbus_register_id', 'in', regs)],
                          fields=['sensor_code', 'modbus_channel', 'ma_in_min', 'ma_in_max',
                                  'eng_out_min', 'eng_out_max', 'filtro_tipo', 'filtro_alpha',
                                  'unidade', 'protocolo_origem', 'area_id', 'measurement_type_id'])
            canais = []
            for s in sensores:
                canal = {
                    'ch': s['modbus_channel'],
                    'sensor_id': s['sensor_code'],
                    'area_id': s['area_id'][1] if s.get('area_id') else None,
                    'tipo_medida': s['measurement_type_id'][1] if s.get('measurement_type_id') else None,
                    'unidade': s.get('unidade') or '',
                    'protocolo_origem': '4-20ma',
                    'map': {'in': [s['ma_in_min'], s['ma_in_max']],
                            'out': [s['eng_out_min'], s['eng_out_max']]},
                }
                if s['filtro_tipo'] != 'none':
                    canal['filtro'] = {'tipo': s['filtro_tipo'], 'alpha': s['filtro_alpha']}
                canais.append(canal)
            dispositivos.append({'endereco': dev['slave_address'], 'driver': driver, 'canais': canais})
        barramentos.append({
            'porta': bus['serial_port'], 'baud': bus['baud_rate'],
            'paridade': bus['parity'], 'stop_bits': int(bus['stop_bits']),
            'dispositivos': dispositivos,
        })

    return {
        'version': hub['config_version_desejada'],
        'intervalo_leitura_s': 5,
        'barramentos': barramentos,
    }
```

> Nota: `area_id`/`measurement_type_id` — confirmar os nomes reais dos campos no modelo `sensor` (o serializador deve usar o `code`/`name` que o Hub espera nos campos `area_id`/`tipo_medida`). `intervalo_leitura_s` é fixo=5 nesta fatia; virá de um campo do hub numa fatia futura.

- [ ] **Step 4: Rodar e confirmar passa**

Run: `python -m pytest api/tests/test_config_serializer.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/config_publisher.py api/tests/test_config_serializer.py
git commit -m "feat(fase5): serializador Odoo→config.yaml operacional do hub"
```

---

### Task 5: Escritor SFTP (API → SFTPGo)

**Files:**
- Modify: `api/config_publisher.py` (função `escrever_config_sftp`)
- Modify: `api/requirements.txt` (paramiko)
- Test: `api/tests/test_config_sftp.py`

**Interfaces:**
- Consumes: conta de serviço SFTP no SFTPGo (env `SFTP_HOST`, `SFTP_PORT`, `SFTP_USER`, `SFTP_KEY_PATH`), dir base `/config`.
- Produces: `escrever_config_sftp(hub_code: str, version: int, conteudo_yaml: str) -> str` — grava `/config/<hub_code>/config-v<version>.yaml` no SFTPGo, devolve o caminho remoto. Cria o dir se preciso.

> Pré-requisito operacional (não é código): criar no SFTPGo (WebAdmin :8190) uma conta de serviço com permissão de escrita em `/config`, e por hub uma conta com leitura em `/config/<hub_code>` e escrita em `/uploads`. Documentar no runbook. Para o teste, usar a conta de serviço.

- [ ] **Step 1: Escrever o teste (grava e relê via SFTP)**

```python
# api/tests/test_config_sftp.py
import os
import paramiko
import pytest

from api.config_publisher import escrever_config_sftp

pytestmark = pytest.mark.skipif(
    not os.environ.get('SFTP_USER'), reason='conta SFTP de serviço não configurada')


def _ler_remoto(caminho):
    t = paramiko.Transport((os.environ['SFTP_HOST'], int(os.environ.get('SFTP_PORT', '2022'))))
    t.connect(username=os.environ['SFTP_USER'],
              pkey=paramiko.Ed25519Key.from_private_key_file(os.environ['SFTP_KEY_PATH']))
    sftp = paramiko.SFTPClient.from_transport(t)
    with sftp.open(caminho, 'r') as f:
        dados = f.read().decode()
    t.close()
    return dados


def test_escrever_config_sftp_grava_arquivo_versionado():
    remoto = escrever_config_sftp('HUB-CFG-01', 9, 'version: 9\n')
    assert remoto == '/config/HUB-CFG-01/config-v9.yaml'
    assert 'version: 9' in _ler_remoto(remoto)
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `python -m pytest api/tests/test_config_sftp.py -q`
Expected: FAIL (função inexistente) ou SKIP se SFTP não configurado. Configure a conta de serviço e as env antes de prosseguir.

- [ ] **Step 3: Implementar `escrever_config_sftp` (+ paramiko no requirements)**

```python
# api/config_publisher.py — acrescentar
import os
import paramiko

_SFTP_BASE = '/config'


def _sftp_conectar():
    t = paramiko.Transport((os.environ['SFTP_HOST'], int(os.environ.get('SFTP_PORT', '2022'))))
    t.connect(username=os.environ['SFTP_USER'],
              pkey=paramiko.Ed25519Key.from_private_key_file(os.environ['SFTP_KEY_PATH']))
    return t, paramiko.SFTPClient.from_transport(t)


def escrever_config_sftp(hub_code, version, conteudo_yaml):
    t, sftp = _sftp_conectar()
    try:
        dir_hub = f'{_SFTP_BASE}/{hub_code}'
        try:
            sftp.stat(dir_hub)
        except FileNotFoundError:
            sftp.mkdir(dir_hub)
        remoto = f'{dir_hub}/config-v{version}.yaml'
        with sftp.open(remoto, 'w') as f:
            f.write(conteudo_yaml)
        return remoto
    finally:
        t.close()
```

```bash
grep -q paramiko api/requirements.txt || echo 'paramiko>=3.4' >> api/requirements.txt
```

- [ ] **Step 4: Rodar e confirmar passa**

Run: `python -m pytest api/tests/test_config_sftp.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/config_publisher.py api/requirements.txt api/tests/test_config_sftp.py
git commit -m "feat(fase5): escritor SFTP da config no SFTPGo (config-vN.yaml por hub)"
```

---

### Task 6: Rota interna de publicação

**Files:**
- Create: `api/config_publish_router.py`
- Modify: `api/main.py` (incluir o router)
- Test: `api/tests/test_config_publish_route.py`

**Interfaces:**
- Consumes: `serializar_config_hub`, `escrever_config_sftp` (Task 4/5), `api.mqtt.publicar` (Task 2), env `CONFIG_PUBLISH_SECRET`.
- Produces: `POST /internal/hub/{hub_code}/publicar-config` header `X-Config-Secret: <secret>` → serializa (usa `config_version_desejada` atual) → grava SFTP → publica `sentinela/config/notify/hub/<code>` retido `{version, publicado_em}` → responde `{"version": N, "arquivo": "..."}`. 401 se secret errado.

- [ ] **Step 1: Escrever o teste da rota**

```python
# api/tests/test_config_publish_route.py
import json
import os
import time

import paho.mqtt.client as mqtt
from fastapi.testclient import TestClient

from api.main import app
from api.odoo import get_cliente_servico
from ingestao import odoo_cliente

client = TestClient(app)
SECRET = os.environ.get('CONFIG_PUBLISH_SECRET', 'test-secret')
MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))


def test_publicar_config_sem_secret_401():
    r = client.post('/internal/hub/HUB-CFG-01/publicar-config')
    assert r.status_code == 401


def test_publicar_config_grava_e_notifica_retido():
    # garante hub provisionado (reusa o fixture da Task 4)
    from api.tests.test_config_serializer import _prov_hub_modbus
    _prov_hub_modbus(get_cliente_servico())

    got = []
    sub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    sub.on_message = lambda c, u, m: got.append(json.loads(m.payload))
    sub.connect(MQTT_HOST, MQTT_PORT, 30)
    sub.subscribe('sentinela/config/notify/hub/HUB-CFG-01', qos=1)
    sub.loop_start()
    time.sleep(0.3)

    r = client.post('/internal/hub/HUB-CFG-01/publicar-config',
                    headers={'X-Config-Secret': SECRET})
    assert r.status_code == 200
    versao = r.json()['version']

    fim = time.time() + 4
    while time.time() < fim and not got:
        time.sleep(0.05)
    sub.loop_stop()
    assert got and got[-1]['version'] == versao
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `CONFIG_PUBLISH_SECRET=test-secret python -m pytest api/tests/test_config_publish_route.py -q`
Expected: FAIL (rota inexistente / 404).

- [ ] **Step 3: Implementar o router**

```python
# api/config_publish_router.py
import os
from datetime import datetime, timezone

import yaml
from fastapi import APIRouter, Header, HTTPException

from . import mqtt as api_mqtt
from .config_publisher import escrever_config_sftp, serializar_config_hub
from .odoo import get_cliente_servico

router = APIRouter()
_SECRET = os.environ.get('CONFIG_PUBLISH_SECRET', '')


@router.post('/internal/hub/{hub_code}/publicar-config')
def publicar_config(hub_code: str, x_config_secret: str = Header(default='')):
    if not _SECRET or x_config_secret != _SECRET:
        raise HTTPException(status_code=401, detail='secret inválido')
    cliente = get_cliente_servico()
    cfg = serializar_config_hub(cliente, hub_code)
    versao = cfg['version']
    remoto = escrever_config_sftp(hub_code, versao, yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))
    api_mqtt.publicar(
        f'sentinela/config/notify/hub/{hub_code}',
        {'version': versao, 'publicado_em': datetime.now(timezone.utc).isoformat()},
        retain=True)
    return {'version': versao, 'arquivo': remoto}
```

```python
# api/main.py — incluir (ao lado dos outros include_router)
from . import config_publish_router
app.include_router(config_publish_router.router)
```

- [ ] **Step 4: Rodar e confirmar passa**

Run: `CONFIG_PUBLISH_SECRET=test-secret python -m pytest api/tests/test_config_publish_route.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/config_publish_router.py api/main.py api/tests/test_config_publish_route.py
git commit -m "feat(fase5): rota interna de publicação (serializa+SFTP+notify retido)"
```

---

### Task 7: Botão "Publicar configuração" no Odoo

**Files:**
- Modify: `addons/afr_sentinela_sensor_monitor/models/hub.py` (método de ação + campo drift)
- Modify: view do hub (botão no form + campos de versão/drift)
- Test: `addons/afr_sentinela_sensor_monitor/tests/test_publicar_config.py`

**Interfaces:**
- Consumes: `ir.config_parameter` `sentinela.api_url`, `sentinela.config_publish_secret`.
- Produces: `hub.action_publicar_config()` — `config_version_desejada += 1`; `requests.post(f'{api_url}/internal/hub/{hub_code}/publicar-config', headers={'X-Config-Secret': secret})`; `message_post` no chatter; campo computado `config_em_drift = (config_version_desejada != config_version_aplicada)`.

- [ ] **Step 1: Escrever o teste (mock do requests)**

```python
# addons/afr_sentinela_sensor_monitor/tests/test_publicar_config.py
from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestPublicarConfig(TransactionCase):
    def _hub(self):
        site = self.env['sensor_monitor.site'].create({
            'name': 'S', 'partner_id': self.env['res.partner'].create({'name': 'P'}).id,
            'site_code': 'SITE-PUB-01', 'vertical': 'cme_hospitalar'})
        return self.env['sensor_monitor.hub'].create({
            'name': 'H', 'site_id': site.id, 'hub_code': 'HUB-PUB-01'})

    def test_publicar_incrementa_versao_e_chama_api(self):
        self.env['ir.config_parameter'].sudo().set_param('sentinela.api_url', 'http://api:8000')
        self.env['ir.config_parameter'].sudo().set_param('sentinela.config_publish_secret', 's3cr3t')
        hub = self._hub()
        v0 = hub.config_version_desejada
        with patch('requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            hub.action_publicar_config()
            assert hub.config_version_desejada == v0 + 1
            args, kwargs = mock_post.call_args
            assert 'HUB-PUB-01/publicar-config' in args[0]
            assert kwargs['headers']['X-Config-Secret'] == 's3cr3t'

    def test_drift_computado(self):
        hub = self._hub()
        hub.config_version_desejada = 5
        hub.config_version_aplicada = 4
        assert hub.config_em_drift is True
        hub.config_version_aplicada = 5
        assert hub.config_em_drift is False
```

- [ ] **Step 2: Rodar e confirmar falha**

Run:
```bash
docker compose exec -T odoo odoo -d sentinela --test-enable --test-tags /afr_sentinela_sensor_monitor:TestPublicarConfig --stop-after-init -u afr_sentinela_sensor_monitor 2>&1 | tail -20
```
Expected: FAIL (método/campo inexistente).

- [ ] **Step 3: Implementar ação + campo drift no hub**

```python
# addons/afr_sentinela_sensor_monitor/models/hub.py — na classe do hub
import requests
from odoo import api, fields, models


    config_em_drift = fields.Boolean(compute='_compute_drift')

    @api.depends('config_version_desejada', 'config_version_aplicada')
    def _compute_drift(self):
        for h in self:
            h.config_em_drift = h.config_version_desejada != h.config_version_aplicada

    def action_publicar_config(self):
        self.ensure_one()
        params = self.env['ir.config_parameter'].sudo()
        api_url = params.get_param('sentinela.api_url')
        secret = params.get_param('sentinela.config_publish_secret')
        self.config_version_desejada += 1
        resp = requests.post(
            f'{api_url}/internal/hub/{self.hub_code}/publicar-config',
            headers={'X-Config-Secret': secret}, timeout=15)
        if resp.status_code != 200:
            self.message_post(body=f'Falha ao publicar config: HTTP {resp.status_code}')
            raise UserError('Falha ao publicar configuração (ver chatter).')
        self.message_post(body=f'Configuração v{self.config_version_desejada} publicada.')
```

> Nota: importar `UserError` de `odoo.exceptions`. A checagem de presença (aviso se hub morto) entra na Task 8 — aqui a ação só publica.

- [ ] **Step 4: Adicionar o botão e os campos no form do hub (XML)**

```xml
<button name="action_publicar_config" type="object" string="Publicar configuração" class="btn-primary"/>
<field name="config_version_desejada"/>
<field name="config_version_aplicada"/>
<field name="config_version_reportada_em"/>
<field name="config_em_drift"/>
```

- [ ] **Step 5: Rodar e confirmar passa**

Run:
```bash
docker compose exec -T odoo odoo -d sentinela --test-enable --test-tags /afr_sentinela_sensor_monitor:TestPublicarConfig --stop-after-init -u afr_sentinela_sensor_monitor 2>&1 | tail -20
```
Expected: `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor/models/hub.py \
        addons/afr_sentinela_sensor_monitor/views/ \
        addons/afr_sentinela_sensor_monitor/tests/test_publicar_config.py
git commit -m "feat(fase5): botão Publicar configuração + campo de drift no hub"
```

---

### Task 8: Rastreador de presença + endpoint de status

**Files:**
- Create: `api/presenca.py`
- Modify: `api/main.py` (startup task) + `api/config_publish_router.py` (endpoint de status)
- Test: `api/tests/test_presenca.py`

**Interfaces:**
- Consumes: `api.mqtt.OuvinteMqtt` (Task 2).
- Produces:
  - `api/presenca.py`: `RASTREADOR` (singleton) com `atualizar(hub_code, dados)`, `estado(hub_code) -> dict|None` (`{estado, heartbeat_ts, idade_s}`), e `iniciar()`/`parar()` que assinam `sentinela/status/hub/#`.
  - `GET /internal/hub/{hub_code}/status` → `{estado, idade_s, stale}` (stale se `idade_s > 90`), 404 se nunca visto.

- [ ] **Step 1: Escrever o teste**

```python
# api/tests/test_presenca.py
import os
import time

import paho.mqtt.client as mqtt
import json
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)
MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))


def test_status_reflete_presenca_publicada():
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.connect(MQTT_HOST, MQTT_PORT, 30)
    c.publish('sentinela/status/hub/HUB-PRES-01',
              json.dumps({'estado': 'online', 'heartbeat_ts': time.time()}),
              qos=1, retain=True)
    c.disconnect()
    time.sleep(1.0)  # deixa o rastreador (startup) consumir

    r = client.get('/internal/hub/HUB-PRES-01/status')
    assert r.status_code == 200
    assert r.json()['estado'] == 'online' and r.json()['stale'] is False

    # limpeza do retido
    c2 = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c2.connect(MQTT_HOST, MQTT_PORT, 30)
    c2.publish('sentinela/status/hub/HUB-PRES-01', '', qos=1, retain=True)
    c2.disconnect()
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `python -m pytest api/tests/test_presenca.py -q`
Expected: FAIL (endpoint 404 / rastreador ausente).

- [ ] **Step 3: Implementar o rastreador**

```python
# api/presenca.py
import time

from .mqtt import OuvinteMqtt

_STALE_S = 90


class Rastreador:
    def __init__(self):
        self._estado = {}
        self._ouvinte = None

    def atualizar(self, topico, dados):
        # topico: sentinela/status/hub/<code>
        code = topico.rsplit('/', 1)[-1]
        self._estado[code] = dados

    def estado(self, hub_code):
        d = self._estado.get(hub_code)
        if not d:
            return None
        idade = time.time() - d.get('heartbeat_ts', 0)
        return {'estado': d.get('estado'), 'idade_s': idade, 'stale': idade > _STALE_S}

    def iniciar(self):
        self._ouvinte = OuvinteMqtt(self.atualizar)
        self._ouvinte.iniciar(['sentinela/status/hub/#'])

    def parar(self):
        if self._ouvinte:
            self._ouvinte.parar()


RASTREADOR = Rastreador()
```

```python
# api/config_publish_router.py — acrescentar endpoint
from .presenca import RASTREADOR


@router.get('/internal/hub/{hub_code}/status')
def status_hub(hub_code: str):
    est = RASTREADOR.estado(hub_code)
    if est is None:
        raise HTTPException(status_code=404, detail='hub nunca reportou presença')
    return est
```

```python
# api/main.py — no startup, iniciar o rastreador
from . import presenca

@app.on_event('startup')
async def _iniciar_presenca():
    presenca.RASTREADOR.iniciar()
```

- [ ] **Step 4: Rodar e confirmar passa**

Run: `python -m pytest api/tests/test_presenca.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/presenca.py api/config_publish_router.py api/main.py api/tests/test_presenca.py
git commit -m "feat(fase5): rastreador de presença do hub + endpoint /status"
```

---

### Task 9: Subscriber de report + fecha o drift

**Files:**
- Create: `api/config_report.py`
- Modify: `api/main.py` (startup task)
- Test: `api/tests/test_config_report.py`

**Interfaces:**
- Consumes: `api.mqtt.OuvinteMqtt`, `get_cliente_servico`, `odoo_cliente.executar`.
- Produces: `api/config_report.py` com `OuvinteReport` que assina `sentinela/config/applied/hub/#`; ao receber `{version:N, aplicado_em, status:'ok'}` grava no hub do Odoo `config_version_aplicada=N` + `config_version_reportada_em=aplicado_em` (via XML-RPC). `status:'erro'` não grava a versão.

- [ ] **Step 1: Escrever o teste**

```python
# api/tests/test_config_report.py
import json
import os
import time

import paho.mqtt.client as mqtt

from api.odoo import get_cliente_servico
from ingestao import odoo_cliente

MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))


def test_applied_fecha_drift_no_odoo():
    cliente = get_cliente_servico()
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)
    site = ex('sensor_monitor.site', 'search', [('site_code', '=', 'SITE-RPT-01')]) or [
        ex('sensor_monitor.site', 'create', {
            'name': 'S', 'partner_id': ex('res.partner', 'search', [], limit=1)[0],
            'site_code': 'SITE-RPT-01', 'vertical': 'cme_hospitalar'})]
    hub = ex('sensor_monitor.hub', 'search', [('hub_code', '=', 'HUB-RPT-01')]) or [
        ex('sensor_monitor.hub', 'create', {'name': 'H', 'site_id': site[0], 'hub_code': 'HUB-RPT-01'})]
    ex('sensor_monitor.hub', 'write', [hub[0]], {'config_version_desejada': 8, 'config_version_aplicada': 0})

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.connect(MQTT_HOST, MQTT_PORT, 30)
    c.publish('sentinela/config/applied/hub/HUB-RPT-01',
              json.dumps({'version': 8, 'aplicado_em': '2026-07-22T10:00:00+00:00', 'status': 'ok'}),
              qos=1)
    c.disconnect()

    fim = time.time() + 6
    aplicada = 0
    while time.time() < fim:
        aplicada = ex('sensor_monitor.hub', 'read', [hub[0]], fields=['config_version_aplicada'])[0]['config_version_aplicada']
        if aplicada == 8:
            break
        time.sleep(0.3)
    assert aplicada == 8
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `python -m pytest api/tests/test_config_report.py -q`
Expected: FAIL (versão aplicada continua 0 — nada consome o applied).

- [ ] **Step 3: Implementar o subscriber de report**

```python
# api/config_report.py
from .mqtt import OuvinteMqtt
from .odoo import get_cliente_servico
from ingestao import odoo_cliente


class OuvinteReport:
    def __init__(self):
        self._ouvinte = None

    def _on(self, topico, dados):
        if dados.get('status') and dados['status'] != 'ok':
            return
        code = topico.rsplit('/', 1)[-1]
        versao = dados.get('version')
        if versao is None:
            return
        cliente = get_cliente_servico()
        hubs = odoo_cliente.executar(cliente, 'sensor_monitor.hub', 'search',
                                     [('hub_code', '=', code)])
        if not hubs:
            return
        odoo_cliente.executar(cliente, 'sensor_monitor.hub', 'write', [hubs[0]], {
            'config_version_aplicada': versao,
            'config_version_reportada_em': dados.get('aplicado_em'),
        })

    def iniciar(self):
        self._ouvinte = OuvinteMqtt(self._on)
        self._ouvinte.iniciar(['sentinela/config/applied/hub/#'])

    def parar(self):
        if self._ouvinte:
            self._ouvinte.parar()


OUVINTE_REPORT = OuvinteReport()
```

```python
# api/main.py — startup
from . import config_report

@app.on_event('startup')
async def _iniciar_report():
    config_report.OUVINTE_REPORT.iniciar()
```

> Nota: `config_version_reportada_em` é Datetime no Odoo — o XML-RPC aceita string ISO; se der erro de formato, converter para `YYYY-MM-DD HH:MM:SS` antes do write.

- [ ] **Step 4: Rodar e confirmar passa**

Run: `python -m pytest api/tests/test_config_report.py -q`
Expected: PASS.

- [ ] **Step 5: Rodar a suíte da API inteira (sem regressão)**

Run: `SKIP_STACK=1 python -m pytest api -q`
Expected: tudo verde (incluindo os testes novos das Tasks 1-9).

- [ ] **Step 6: Commit**

```bash
git add api/config_report.py api/main.py api/tests/test_config_report.py
git commit -m "feat(fase5): subscriber de applied fecha o drift no Odoo"
```

---

## Encerramento do Plano A

Ao fim das 9 tasks, o servidor: publica a config Modbus de um hub (arquivo SFTP + notify retido), rastreia presença, e fecha o drift ao receber `applied` — tudo verificável no Docker com clientes MQTT de teste, sem o Pi. **Próximo:** Plano B (config-agent no Hub real + SFTP download no cliente existente + apply/reload do leitor + ack/applied + runbook E2E lendo o N4AIB16).

## Self-Review (feita)
- **Cobertura da spec:** §4.1 (Mosquitto T1, serializador T4, publisher/subscriber T2/T6/T9, presença T8, botão/drift T7), §5.1 tópicos (T6 notify, T8 status, T9 applied), §5.2 arquivo SFTP (T5), §5.3 subconjunto operacional (T4), §7 modelo (T3), §8 secret (T6). Ack (§5.1) e `status:erro` no chatter são consumidos no Plano B (lado hub emite) — subscriber de ack fica no B junto do agente que o emite.
- **Placeholders:** os dois "Nota p/ implementador" (fixture reusando `provisionar_demo`; nomes reais de `area_id`/`measurement_type`) são pontos de confirmação contra o código real, não lacunas de design — o implementador confirma os nomes dos campos ao abrir o modelo `sensor`.
- **Consistência de tipos:** `serializar_config_hub(cliente, hub_code)->dict`, `escrever_config_sftp(hub_code,version,yaml)->str`, `api_mqtt.publicar(topico,payload,retain)`, `OuvinteMqtt(on_mensagem)`/`.iniciar(topicos)`/`.parar()` usados consistentes entre T2/T4/T5/T6/T8/T9.
