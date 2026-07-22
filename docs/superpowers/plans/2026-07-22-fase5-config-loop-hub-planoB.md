# Fase 5 — Config loop (Plano B: Hub real) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lado Hub do laço de configuração — o Pi recebe o sinal MQTT, baixa a config por SFTP, funde com a identidade local, aplica, recarrega o leitor, e reporta de volta; mais uma extensão no servidor (heartbeat retido fecha o drift) e a prova E2E lendo o N4AIB16 real (CH1=18,4mA).

**Architecture:** No Hub (`hub/`): um cliente MQTT de control-plane separado (`AgenteControle`) com LWT + heartbeat retido; ao receber `notify{version:N}` baixa `/config/<code>/config-vN.yaml`, funde com `identity.yaml` local (via `identidade_config`), escreve o `config.yaml` efetivo, sinaliza reload (Event) e publica `ack`/`applied`. O loop leitor (`main.py::executar`), único dono da serial, fecha/reabre o `Leitor` entre ciclos ao ver o Event. No servidor: o rastreador de presença lê `config_version_aplicada` do heartbeat retido e fecha o drift (rede de segurança do `applied` não-retido).

**Tech Stack:** Python, paho-mqtt, paramiko, PyYAML, pytest. Hub roda no Raspberry Pi (aarch64); código testado localmente (unit) + E2E no Pi.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-22-fase5-config-loop-hub-planoB-design.md` (+ pai `2026-07-21-fase5-config-loop-hardware-design.md`).
- Tópicos MQTT (exatos): `sentinela/status/hub/<code>` (retido+LWT), `sentinela/config/notify/hub/<code>` (retido), `sentinela/config/ack/hub/<code>`, `sentinela/config/applied/hub/<code>`. `<code>` = hub_code.
- **Datetime em `ack`/`applied`/heartbeat: ISO com `+00:00`, NUNCA `Z`** (subscriber do servidor usa `datetime.fromisoformat` no Python 3.9).
- **Identidade/creds NUNCA vêm do servidor** (`identity.yaml` local): `hub_id`, `coletor_id`, `firmware_version`, `timezone_offset`, `caminho_chave`, `caminho_dados`, `mqtt`, `sftp`. Operacional (baixado): `intervalo_leitura_s`, `barramentos`.
- Contrato do `config.yaml` efetivo = o que `hub/config.py::carregar_config` já parseia (não mudar o parser). `map:{in:[..],out:[..]}` no yaml; `paridade` em `N`/`E`/`O`.
- Heartbeat status retido inclui `config_version_aplicada`.
- Rodar pytest da raiz do repo com `.venv`. Testes de SFTP usam a conta de serviço (env `SFTP_HOST/PORT/USER/KEY_PATH`) já provisionada. Testes de MQTT contra Mosquitto local :1883.
- Reload: o loop leitor é o ÚNICO dono da serial; o callback MQTT só sinaliza via `threading.Event`.
- SFTP: um único SFTPGo (put+get no mesmo cliente).

---

### Task 1: `TransporteParamiko.baixar()` (GET) no cliente SFTP

**Files:**
- Modify: `hub/enviador_sftp.py` (Protocol `Transporte` + `TransporteParamiko`)
- Test: `hub/tests/test_transporte_baixar.py`

**Interfaces:**
- Produces: `Transporte.baixar(caminho_remoto: str, caminho_local: str) -> None` (protocol); `TransporteParamiko.baixar(...)` — GET de um caminho REMOTO ABSOLUTO (ex. `/config/HUB-X/config-v3.yaml`, não relativo ao `remote_dir`) para um arquivo local. Reusa a conexão SSHClient+Ed25519 já usada por `enviar`.

- [ ] **Step 1: Escrever o teste (grava via serviço, baixa via TransporteParamiko)**

```python
# hub/tests/test_transporte_baixar.py
import os
import paramiko
import pytest

from hub.enviador_sftp import TransporteParamiko

pytestmark = pytest.mark.skipif(
    not os.environ.get('SFTP_USER'), reason='conta SFTP de serviço não configurada')


def _subir(caminho_remoto, conteudo):
    t = paramiko.Transport((os.environ['SFTP_HOST'], int(os.environ.get('SFTP_PORT', '2022'))))
    t.connect(username=os.environ['SFTP_USER'],
              pkey=paramiko.Ed25519Key.from_private_key_file(os.environ['SFTP_KEY_PATH']))
    sftp = paramiko.SFTPClient.from_transport(t)
    try:
        sftp.stat('/config/HUB-BAIXAR')
    except FileNotFoundError:
        sftp.mkdir('/config/HUB-BAIXAR')
    with sftp.open(caminho_remoto, 'w') as f:
        f.write(conteudo)
    t.close()


def test_baixar_traz_arquivo_remoto(tmp_path):
    remoto = '/config/HUB-BAIXAR/config-v3.yaml'
    _subir(remoto, 'version: 3\n')
    transporte = TransporteParamiko(
        os.environ['SFTP_HOST'], int(os.environ.get('SFTP_PORT', '2022')),
        os.environ['SFTP_USER'], os.environ['SFTP_KEY_PATH'], '/uploads')
    destino = tmp_path / 'baixado.yaml'
    transporte.baixar(remoto, str(destino))
    assert destino.read_text() == 'version: 3\n'
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `source .venv/bin/activate && export SFTP_HOST=localhost SFTP_PORT=2022 SFTP_USER=sentinela-config-svc SFTP_KEY_PATH=/home/afonso/docker/odoo_sentinela/.sftp-config-svc/id_ed25519 && python -m pytest hub/tests/test_transporte_baixar.py -q`
Expected: FAIL (`AttributeError: ... has no attribute 'baixar'`). NÃO deve dar SKIP (env exportada).

- [ ] **Step 3: Adicionar `baixar` ao Protocol e ao TransporteParamiko**

```python
# hub/enviador_sftp.py — no Protocol Transporte, junto de enviar:
    def baixar(self, caminho_remoto: str, caminho_local: str) -> None: ...
```

```python
# hub/enviador_sftp.py — na classe TransporteParamiko, novo método:
    def baixar(self, caminho_remoto, caminho_local):
        import paramiko
        chave = paramiko.Ed25519Key.from_private_key_file(self._ssh_key_path)
        cliente = paramiko.SSHClient()
        cliente.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cliente.connect(self._host, port=self._port, username=self._username,
                        pkey=chave, look_for_keys=False, allow_agent=False)
        try:
            sftp = cliente.open_sftp()
            sftp.get(caminho_remoto, caminho_local)
            sftp.close()
        finally:
            cliente.close()
```

- [ ] **Step 4: Rodar e confirmar passa**

Run: (mesma env) `python -m pytest hub/tests/test_transporte_baixar.py -q`
Expected: PASS (não SKIP).

- [ ] **Step 5: Commit**

```bash
git add hub/enviador_sftp.py hub/tests/test_transporte_baixar.py
git commit -m "feat(fase5-hub): TransporteParamiko.baixar (GET) — cliente SFTP put+get"
```

---

### Task 2: `identidade_config` — split identidade/operacional + merge

**Files:**
- Create: `hub/identidade_config.py`
- Test: `hub/tests/test_identidade_config.py`

**Interfaces:**
- Consumes: `hub/config.py::carregar_config` (para validar que o efetivo carrega).
- Produces:
  - `carregar_identidade(caminho) -> dict` — lê `identity.yaml`.
  - `fundir(identidade: dict, operacional: dict) -> dict` — sobrepõe operacional sobre identidade → dict completo do contrato config.yaml.
  - `escrever_config_efetivo(merged: dict, caminho) -> None` — grava yaml.

- [ ] **Step 1: Escrever o teste**

```python
# hub/tests/test_identidade_config.py
import yaml

from hub import config as config_mod
from hub.identidade_config import carregar_identidade, escrever_config_efetivo, fundir

IDENTIDADE = {
    'hub_id': 'HUB-0001A2F3', 'coletor_id': 'COL-RS485-BUS0',
    'firmware_version': '0.1.0', 'timezone_offset': '-03:00',
    'caminho_chave': '~/sentinela-hub/chaves/coletor.pem',
    'caminho_dados': '~/sentinela-hub/dados',
    'mqtt': {'host': 'localhost', 'port': 1883},
    'sftp': {'host': '10.8.0.1', 'port': 2022, 'username': 'hub-x',
             'ssh_key_path': '~/k', 'remote_dir': '/uploads'},
}
OPERACIONAL = {
    'version': 4, 'intervalo_leitura_s': 5,
    'barramentos': [{'porta': '/dev/ttyUSB0', 'baud': 9600, 'paridade': 'N', 'stop_bits': 1,
        'dispositivos': [{'endereco': 1, 'driver': 'n4aib16', 'canais': [
            {'ch': 1, 'sensor_id': 'SNR-EXP-TEMP-01', 'area_id': 'AREA-EXPURGO',
             'tipo_medida': 'temperatura', 'unidade': 'C', 'protocolo_origem': '4-20ma',
             'map': {'in': [4, 20], 'out': [-50, 150]}}]}]}],
}


def test_fundir_sobrepoe_operacional_sem_vazar_identidade():
    merged = fundir(IDENTIDADE, OPERACIONAL)
    assert merged['intervalo_leitura_s'] == 5
    assert merged['barramentos'] == OPERACIONAL['barramentos']
    assert merged['hub_id'] == 'HUB-0001A2F3'  # identidade preservada
    assert merged['sftp']['username'] == 'hub-x'


def test_efetivo_carrega_no_config_py(tmp_path):
    merged = fundir(IDENTIDADE, OPERACIONAL)
    caminho = tmp_path / 'config.yaml'
    escrever_config_efetivo(merged, str(caminho))
    cfg = config_mod.carregar_config(str(caminho))  # não deve levantar
    assert cfg.intervalo_leitura_s == 5
    assert cfg.barramentos[0].dispositivos[0].canais[0].sensor_id == 'SNR-EXP-TEMP-01'
    assert cfg.barramentos[0].dispositivos[0].canais[0].map_in == (4.0, 20.0)


def test_carregar_identidade_le_yaml(tmp_path):
    p = tmp_path / 'identity.yaml'
    p.write_text(yaml.safe_dump(IDENTIDADE))
    assert carregar_identidade(str(p))['hub_id'] == 'HUB-0001A2F3'
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `source .venv/bin/activate && python -m pytest hub/tests/test_identidade_config.py -q`
Expected: FAIL (`ModuleNotFoundError: hub.identidade_config`).

- [ ] **Step 3: Implementar**

```python
# hub/identidade_config.py
from pathlib import Path

import yaml


def carregar_identidade(caminho):
    return yaml.safe_load(Path(caminho).expanduser().read_text())


def fundir(identidade, operacional):
    merged = dict(identidade)
    merged['intervalo_leitura_s'] = operacional['intervalo_leitura_s']
    merged['barramentos'] = operacional['barramentos']
    return merged


def escrever_config_efetivo(merged, caminho):
    Path(caminho).expanduser().write_text(
        yaml.safe_dump(merged, sort_keys=False, allow_unicode=True))
```

- [ ] **Step 4: Rodar e confirmar passa**

Run: `python -m pytest hub/tests/test_identidade_config.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add hub/identidade_config.py hub/tests/test_identidade_config.py
git commit -m "feat(fase5-hub): split identity.yaml + merge → config.yaml efetivo"
```

---

### Task 3: `AgenteControle` — control-plane MQTT + notify→download→apply→report

**Files:**
- Create: `hub/agente_config.py`
- Test: `hub/tests/test_agente_config.py`

**Interfaces:**
- Consumes: `identidade_config.fundir/escrever_config_efetivo`, um callable `sftp_baixar(caminho_remoto, caminho_local)`, um `threading.Event` `reconfigurar`.
- Produces: `class AgenteControle` com:
  - `__init__(self, hub_code, identidade, sftp_baixar, reconfigurar, caminho_config, estado_path, fw='0.1.0', client=None, agora_fn=None)`
  - `processar_notify(self, dados: dict) -> None` — a lógica central (testável sem MQTT): se `dados['version'] > self.aplicada`: baixa, funde, escreve efetivo, avança `self.aplicada`, persiste, `reconfigurar.set()`, e retorna o payload `applied` publicado; em erro publica `applied status:'erro'`.
  - `heartbeat_payload(self) -> dict` — `{estado:'online', heartbeat_ts, fw, config_version_aplicada}`.
  - `iniciar()`/`parar()` — MQTT real (LWT, connect_async, on_connect resubscribe + publica heartbeat, on_message→processar_notify).
  - `self.aplicada` carregado de `estado_path` no `__init__` (default 0).

- [ ] **Step 1: Escrever o teste (lógica pura, MQTT e SFTP injetados/mockados)**

```python
# hub/tests/test_agente_config.py
import json
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock

import yaml

from hub.agente_config import AgenteControle
from hub.tests._fixtures_config import IDENTIDADE, OPERACIONAL  # reusa Task 2 (ver nota)


def _agente(tmp_path, publish, sftp_baixar):
    client = MagicMock()
    client.publish = publish
    ag = AgenteControle(
        hub_code='HUB-EXP', identidade=IDENTIDADE, sftp_baixar=sftp_baixar,
        reconfigurar=Event(), caminho_config=str(tmp_path / 'config.yaml'),
        estado_path=str(tmp_path / 'estado.json'), fw='0.1.0', client=client,
        agora_fn=lambda: __import__('datetime').datetime(2026, 7, 22, 10, 0, 0,
                       tzinfo=__import__('datetime').timezone.utc))
    return ag


def test_notify_nova_versao_baixa_aplica_e_reporta(tmp_path):
    publicados = []
    def publish(topico, payload, **k): publicados.append((topico, json.loads(payload)))
    def sftp_baixar(remoto, local):
        Path(local).write_text(yaml.safe_dump(OPERACIONAL))  # simula o download
    ag = _agente(tmp_path, publish, sftp_baixar)
    ag.processar_notify({'version': 4})
    # efetivo escrito e carregável
    assert (tmp_path / 'config.yaml').exists()
    # estado avançou e persistiu
    assert ag.aplicada == 4
    assert json.loads((tmp_path / 'estado.json').read_text())['config_version_aplicada'] == 4
    # reconfigurar sinalizado
    assert ag._reconfigurar.is_set()
    # applied publicado com +00:00 (não Z) e status ok
    applied = [p for t, p in publicados if t.endswith('applied/hub/HUB-EXP')][-1]
    assert applied['version'] == 4 and applied['status'] == 'ok'
    assert applied['aplicado_em'].endswith('+00:00') and 'Z' not in applied['aplicado_em']


def test_notify_versao_antiga_e_noop(tmp_path):
    ag = _agente(tmp_path, lambda *a, **k: None, lambda *a, **k: None)
    ag.aplicada = 5
    ag.processar_notify({'version': 3})
    assert ag.aplicada == 5 and not ag._reconfigurar.is_set()


def test_erro_no_download_publica_status_erro(tmp_path):
    publicados = []
    def publish(topico, payload, **k): publicados.append((topico, json.loads(payload)))
    def sftp_baixar(remoto, local): raise OSError('sem rede')
    ag = _agente(tmp_path, publish, sftp_baixar)
    ag.processar_notify({'version': 7})
    assert ag.aplicada == 0  # não avançou
    applied = [p for t, p in publicados if 'applied' in t][-1]
    assert applied['version'] == 7 and applied['status'] == 'erro'


def test_heartbeat_inclui_versao_aplicada(tmp_path):
    ag = _agente(tmp_path, lambda *a, **k: None, lambda *a, **k: None)
    ag.aplicada = 6
    hb = ag.heartbeat_payload()
    assert hb['estado'] == 'online' and hb['config_version_aplicada'] == 6 and 'heartbeat_ts' in hb
```

> Nota p/ o implementer: crie `hub/tests/_fixtures_config.py` com as constantes `IDENTIDADE` e `OPERACIONAL` (as mesmas do teste da Task 2) para reuso; ou importe de onde preferir. Mantenha `IDENTIDADE`/`OPERACIONAL` idênticas às da Task 2.

- [ ] **Step 2: Rodar e confirmar falha**

Run: `source .venv/bin/activate && python -m pytest hub/tests/test_agente_config.py -q`
Expected: FAIL (`ModuleNotFoundError: hub.agente_config`).

- [ ] **Step 3: Implementar `AgenteControle`**

```python
# hub/agente_config.py
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from hub.identidade_config import escrever_config_efetivo, fundir

_KEEPALIVE = 30


def _iso_utc(agora_fn):
    return agora_fn().astimezone(timezone.utc).isoformat()  # +00:00, nunca Z


class AgenteControle:
    def __init__(self, hub_code, identidade, sftp_baixar, reconfigurar, caminho_config,
                 estado_path, fw='0.1.0', client=None, mqtt_host='localhost',
                 mqtt_port=1883, agora_fn=None):
        self._code = hub_code
        self._identidade = identidade
        self._baixar = sftp_baixar
        self._reconfigurar = reconfigurar
        self._caminho_config = caminho_config
        self._estado_path = Path(estado_path)
        self._fw = fw
        self._host = mqtt_host
        self._port = mqtt_port
        self._agora = agora_fn or (lambda: datetime.now(timezone.utc))
        self.aplicada = self._carregar_estado()
        if client is None:
            import paho.mqtt.client as mqtt
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client = client

    def _carregar_estado(self):
        if self._estado_path.exists():
            return int(json.loads(self._estado_path.read_text()).get('config_version_aplicada', 0))
        return 0

    def _persistir_estado(self):
        self._estado_path.parent.mkdir(parents=True, exist_ok=True)
        self._estado_path.write_text(json.dumps({'config_version_aplicada': self.aplicada}))

    def _publicar(self, sufixo, payload, retain=False):
        self._client.publish(f'sentinela/config/{sufixo}/hub/{self._code}',
                             json.dumps(payload), qos=1, retain=retain)

    def heartbeat_payload(self):
        return {'estado': 'online', 'heartbeat_ts': _iso_utc(self._agora),
                'fw': self._fw, 'config_version_aplicada': self.aplicada}

    def processar_notify(self, dados):
        versao = dados.get('version')
        if versao is None or versao <= self.aplicada:
            return
        self._client.publish(f'sentinela/config/ack/hub/{self._code}',
                             json.dumps({'version': versao, 'recebido_em': _iso_utc(self._agora)}),
                             qos=1)
        try:
            local_tmp = f'{self._caminho_config}.baixando'
            self._baixar(f'/config/{self._code}/config-v{versao}.yaml', local_tmp)
            operacional = yaml.safe_load(Path(local_tmp).read_text())
            merged = fundir(self._identidade, operacional)
            escrever_config_efetivo(merged, self._caminho_config)
            self.aplicada = versao
            self._persistir_estado()
            self._reconfigurar.set()
            self._publicar('applied', {'version': versao, 'aplicado_em': _iso_utc(self._agora),
                                       'status': 'ok'})
        except Exception as e:
            self._publicar('applied', {'version': versao, 'aplicado_em': _iso_utc(self._agora),
                                       'status': 'erro', 'detalhe': str(e)[:200]})

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        client.subscribe(f'sentinela/config/notify/hub/{self._code}', qos=1)
        client.publish(f'sentinela/status/hub/{self._code}',
                      json.dumps(self.heartbeat_payload()), qos=1, retain=True)

    def _on_message(self, client, userdata, msg):
        try:
            self.processar_notify(json.loads(msg.payload) if msg.payload else {})
        except json.JSONDecodeError:
            pass

    def iniciar(self):
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.will_set(f'sentinela/status/hub/{self._code}',
                             json.dumps({'estado': 'offline'}), qos=1, retain=True)
        self._client.connect_async(self._host, self._port, _KEEPALIVE)
        self._client.loop_start()

    def parar(self):
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except OSError:
            pass
```

- [ ] **Step 4: Rodar e confirmar passa**

Run: `python -m pytest hub/tests/test_agente_config.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add hub/agente_config.py hub/tests/test_agente_config.py hub/tests/_fixtures_config.py
git commit -m "feat(fase5-hub): AgenteControle (control-plane MQTT + notify→SFTP→apply→report)"
```

---

### Task 4: Reload in-loop no `main.py::executar` + wiring do agente

**Files:**
- Modify: `hub/main.py` (`executar` + `main`)
- Test: `hub/tests/test_reload_inloop.py`

**Interfaces:**
- Consumes: `AgenteControle`, `carregar_config`, `Leitor`.
- Produces: `executar(..., reconfigurar=None, caminho_config=None)` — entre ciclos, se `reconfigurar` setado, fecha o leitor, recarrega `carregar_config(caminho_config)`, reconstrói `Leitor`, atualiza intervalo, limpa o Event.

- [ ] **Step 1: Escrever o teste (Leitor e config mockados; prova fechar→reabrir)**

```python
# hub/tests/test_reload_inloop.py
from threading import Event
from unittest.mock import MagicMock

from hub import main as hub_main


def test_executar_recarrega_leitor_quando_reconfigurar_setado(monkeypatch):
    parar = Event()
    reconfig = Event()
    reconfig.set()  # já sinalizado → deve recarregar no 1º ciclo

    leitor_velho = MagicMock()
    leitor_velho.ler_todos.return_value = []
    leitor_novo = MagicMock()
    leitor_novo.ler_todos.return_value = []

    cfg = MagicMock(); cfg.intervalo_leitura_s = 0; cfg.hub_id = 'H'; cfg.coletor_id = 'C'
    cfg_novo = MagicMock(); cfg_novo.intervalo_leitura_s = 0

    monkeypatch.setattr(hub_main.config_mod, 'carregar_config', lambda p: cfg_novo)
    criados = []
    def fake_leitor(c):
        criados.append(c); return leitor_novo
    monkeypatch.setattr(hub_main, 'Leitor', fake_leitor)

    arquivo = MagicMock(); publicador = MagicMock()
    # para no 1º ciclo após recarregar
    def agora():
        parar.set()  # encerra após um ciclo
        import datetime
        return datetime.datetime(2026, 7, 22, tzinfo=datetime.timezone.utc)

    hub_main.executar(cfg, leitor_velho, arquivo, publicador, agora_fn=agora,
                      parar=parar, max_ciclos=1, reconfigurar=reconfig,
                      caminho_config='config.yaml')

    leitor_velho.fechar.assert_called_once()   # leitor antigo fechado
    assert criados == [cfg_novo]               # novo Leitor da config nova
    assert not reconfig.is_set()               # Event limpo
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `source .venv/bin/activate && python -m pytest hub/tests/test_reload_inloop.py -q`
Expected: FAIL (`executar()` não aceita `reconfigurar`/`caminho_config`, ou não recarrega).

- [ ] **Step 3: Modificar `executar` (reload in-loop)**

Substituir a assinatura e o corpo do loop em `hub/main.py::executar`:

```python
def executar(config, leitor, arquivo, publicador, agora_fn, parar, max_ciclos=None,
             enviador=None, reconfigurar=None, caminho_config=None):
    arquivo.recuperar_pendentes(agora_fn().date())
    publicador.conectar()
    ciclos = 0
    data_corrente = None
    intervalo = config.intervalo_leitura_s
    while not parar.is_set():
        if reconfigurar is not None and reconfigurar.is_set():
            leitor.fechar()
            config = config_mod.carregar_config(caminho_config)
            leitor = Leitor(config)
            intervalo = config.intervalo_leitura_s
            reconfigurar.clear()
        agora = agora_fn()
        data_corrente = agora.date().isoformat()
        for leitura in leitor.ler_todos(agora):
            arquivo.registrar(leitura)
            publicador.publicar(config.hub_id, config.coletor_id, leitura)
        if enviador is not None:
            enviador.varrer()
        ciclos += 1
        if max_ciclos is not None and ciclos >= max_ciclos:
            break
        parar.wait(intervalo)
    arquivo.selar(data_corrente)
    if enviador is not None:
        enviador.varrer()
    leitor.fechar()
    publicador.fechar()
```

- [ ] **Step 4: Rodar e confirmar passa**

Run: `python -m pytest hub/tests/test_reload_inloop.py -q`
Expected: PASS.

- [ ] **Step 5: Wire o AgenteControle no `main()`**

Modificar `hub/main.py::main` para: carregar `identity.yaml` (via `--identity`, ou derivar), montar o Event `reconfigurar`, instanciar `AgenteControle` (com `TransporteParamiko(...).baixar` como `sftp_baixar`), iniciar o agente, e passar `reconfigurar` + `caminho_config` ao `executar`. Exemplo mínimo (ajustar aos args reais):

```python
    # em main(), após montar cfg/leitor/publicador/enviador:
    from threading import Event
    from hub.agente_config import AgenteControle
    from hub.identidade_config import carregar_identidade
    reconfigurar = Event()
    agente = None
    if cfg.sftp is not None:
        identidade = carregar_identidade(args.identity)   # novo arg --identity
        agente = AgenteControle(
            hub_code=identidade.get('hub_code', cfg.hub_id),
            identidade=identidade, sftp_baixar=transporte.baixar,
            reconfigurar=reconfigurar, caminho_config=args.config,
            estado_path=str(Path(cfg.caminho_dados).expanduser() / 'estado_config.json'),
            fw=cfg.firmware_version, mqtt_host=cfg.mqtt_host, mqtt_port=cfg.mqtt_port)
        agente.iniciar()
    executar(cfg, leitor, arquivo, publicador, agora_fn=lambda: datetime.now(tz),
             parar=parar, enviador=enviador, reconfigurar=reconfigurar, caminho_config=args.config)
    if agente is not None:
        agente.parar()
```

> Nota: `main()` não tem teste unitário dedicado (é fiação/orquestração com I/O real). Rode `python -m pytest hub -q` (suíte hub inteira) p/ garantir que nada quebrou com a nova assinatura de `executar`. Se `hub_code` não existir no identity, use `hub_id` como fallback (já no exemplo).

- [ ] **Step 6: Rodar suíte hub + commit**

Run: `python -m pytest hub contrato -q`
Expected: verde (todos os testes hub + contrato).

```bash
git add hub/main.py hub/tests/test_reload_inloop.py
git commit -m "feat(fase5-hub): reload in-loop do leitor + wiring do AgenteControle"
```

---

### Task 5: Extensão do servidor — heartbeat retido fecha o drift

**Files:**
- Modify: `api/config_report.py` (extrair função compartilhada)
- Modify: `api/presenca.py` (usar a versão aplicada do heartbeat)
- Test: `api/tests/test_presenca_fecha_drift.py`

**Interfaces:**
- Produces: `api/config_report.py::registrar_versao_aplicada(cliente, hub_code, versao, quando)` — grava `config_version_aplicada`/`config_version_reportada_em` no hub Odoo (só se `versao` avança). Reusado pelo report (Task 9 do Plano A) e pela presença.
- `api/presenca.py::Rastreador.atualizar` — se o status trouxer `config_version_aplicada` maior que o do Odoo, chama `registrar_versao_aplicada`.

- [ ] **Step 1: Escrever o teste**

```python
# api/tests/test_presenca_fecha_drift.py
import json
import os
import time

import paho.mqtt.client as mqtt

from api.odoo import get_cliente_servico
from ingestao import odoo_cliente

MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))


def test_heartbeat_com_versao_aplicada_fecha_drift():
    cliente = get_cliente_servico()
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)
    site = ex('sensor_monitor.site', 'search', [('site_code', '=', 'SITE-HB-01')]) or [
        ex('sensor_monitor.site', 'create', {
            'name': 'S', 'partner_id': ex('res.partner', 'search', [], limit=1)[0],
            'site_code': 'SITE-HB-01', 'vertical': 'cme_hospitalar'})]
    hub = ex('sensor_monitor.hub', 'search', [('hub_code', '=', 'HUB-HB-01')]) or [
        ex('sensor_monitor.hub', 'create', {'name': 'H', 'site_id': site[0], 'hub_code': 'HUB-HB-01'})]
    ex('sensor_monitor.hub', 'write', [hub[0]], {'config_version_desejada': 9, 'config_version_aplicada': 0})

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.connect(MQTT_HOST, MQTT_PORT, 30)
    c.publish('sentinela/status/hub/HUB-HB-01', json.dumps({
        'estado': 'online', 'heartbeat_ts': '2026-07-22T10:00:00+00:00',
        'fw': '0.1.0', 'config_version_aplicada': 9}), qos=1, retain=True)
    c.disconnect()

    fim = time.time() + 8
    aplicada = 0
    while time.time() < fim:
        aplicada = ex('sensor_monitor.hub', 'read', [hub[0]], fields=['config_version_aplicada'])[0]['config_version_aplicada']
        if aplicada == 9:
            break
        time.sleep(0.3)
    # limpa o retido
    c2 = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c2.connect(MQTT_HOST, MQTT_PORT, 30)
    c2.publish('sentinela/status/hub/HUB-HB-01', '', qos=1, retain=True)
    c2.disconnect()
    assert aplicada == 9
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `source .venv/bin/activate && export CONFIG_PUBLISH_SECRET=test-secret MQTT_HOST=localhost MQTT_PORT=1883 SFTP_HOST=localhost SFTP_PORT=2022 SFTP_USER=sentinela-config-svc SFTP_KEY_PATH=/home/afonso/docker/odoo_sentinela/.sftp-config-svc/id_ed25519 && python -m pytest api/tests/test_presenca_fecha_drift.py -q`
Expected: FAIL (presença não escreve a versão aplicada no Odoo).

- [ ] **Step 3: Extrair `registrar_versao_aplicada` em config_report.py**

```python
# api/config_report.py — nova função no topo do módulo (reusa o helper de datetime existente)
def registrar_versao_aplicada(cliente, hub_code, versao, quando):
    from ingestao import odoo_cliente
    hubs = odoo_cliente.executar(cliente, 'sensor_monitor.hub', 'search_read',
                                 [('hub_code', '=', hub_code)],
                                 fields=['id', 'config_version_aplicada'])
    if not hubs or versao <= (hubs[0]['config_version_aplicada'] or 0):
        return
    odoo_cliente.executar(cliente, 'sensor_monitor.hub', 'write', [hubs[0]['id']], {
        'config_version_aplicada': versao,
        'config_version_reportada_em': _formatar_datetime_odoo(quando),
    })
```

E refatorar o `OuvinteReport._on` para chamar `registrar_versao_aplicada(cliente, code, versao, dados.get('aplicado_em'))` em vez do write inline (mantendo o comportamento).

- [ ] **Step 4: Presença usa a versão aplicada do heartbeat**

```python
# api/presenca.py — em atualizar(), após guardar o estado:
    def atualizar(self, topico, dados):
        code = topico.rsplit('/', 1)[-1]
        self._estado[code] = dados
        versao = dados.get('config_version_aplicada')
        if versao:
            from .config_report import registrar_versao_aplicada
            from .odoo import get_cliente_servico
            try:
                registrar_versao_aplicada(get_cliente_servico(), code, int(versao),
                                          dados.get('heartbeat_ts'))
            except Exception:
                pass  # presença é best-effort; não derruba o rastreador
```

- [ ] **Step 5: Rodar e confirmar passa**

Run: (mesma env) `python -m pytest api/tests/test_presenca_fecha_drift.py api/tests/test_config_report.py -q`
Expected: PASS (o teste novo + os da Task 9 do Plano A seguem verdes).

- [ ] **Step 6: Suíte api + commit**

Run: (env completa) `python -m pytest api -q`
Expected: verde.

```bash
git add api/config_report.py api/presenca.py api/tests/test_presenca_fecha_drift.py
git commit -m "feat(fase5): heartbeat retido fecha o drift (rede de segurança do applied)"
```

---

### Task 6: Deploy no Pi + `identity.yaml` + prova E2E (N4AIB16 CH1)

**Files:**
- Create: `docs/runbooks/fase5-config-loop-e2e-hub.md`
- (No Pi) Create: `~/sentinela-hub/identity.yaml`

**Interfaces:** N/A (runbook operacional + execução manual; sem TDD de código). A prova é o critério de sucesso do §7 da spec.

- [ ] **Step 1: Escrever o runbook E2E**

Criar `docs/runbooks/fase5-config-loop-e2e-hub.md` documentando, na ordem:
1. **Sincronizar o Hub no Pi:** `ssh fitadigital@192.168.0.211`, `cd ~/odoo_sentinela`, trazer o código novo do `hub/` (merge/rebase da branch do Plano B em `fix/expanduser-caminho-chave`, ou `git fetch && git checkout` do branch; documentar o comando exato usado). `git submodule update --init` se preciso.
2. **Criar `~/sentinela-hub/identity.yaml`** a partir do `hub/config.example.yaml`, mantendo SÓ: `hub_id`, `coletor_id`, `firmware_version`, `timezone_offset`, `caminho_chave`, `caminho_dados`, `mqtt:{host,port}`, `sftp:{host,port,username,ssh_key_path,remote_dir}`. Adicionar `hub_code: <HUB-REAL>` (o hub_code cadastrado no Odoo). Host do broker/SFTP = IP do servidor no LAN (ou 10.8.0.1 na VPN).
3. **Provisionar no Odoo** (via UI ou script): site + hub `HUB-REAL` (hub_code batendo o identity) + rs485.bus (`/dev/ttyUSB0`, 9600, none, 1) + modbus.profile (driver n4aib16) + register + modbus.device (addr 1) + sensor mapeado a **CH1**: `modbus_channel=1`, `ma_in_min=4`, `ma_in_max=20`, `eng_out_min/eng_out_max` (faixa escolhida, ex. temperatura -50..150), `modbus_register_id`, `protocolo_origem=rs485`.
4. **Publicar** (botão "Publicar configuração" no hub do Odoo). Anotar a versão desejada.
5. **No Pi:** rodar `python -m hub.main --config ~/sentinela-hub/config.yaml --identity ~/sentinela-hub/identity.yaml` (o `config.yaml` será gerado pelo agente no 1º notify; documentar o comportamento de boot-sem-config).
6. **Verificar o laço:**
   - Odoo: drift fecha (desejada==aplicada) — via applied e/ou heartbeat.
   - Pi: `config.yaml` efetivo escrito com a versão publicada; `estado_config.json` = versão.
   - Timescale/Odoo: leitura nova do sensor de CH1 (valor de engenharia derivado de ~18,4mA pela `map`).
   - Dashboard: valor real de CH1 ao vivo.
- **Critério de sucesso:** drift fechado **e** valor real de CH1 no dashboard.

- [ ] **Step 2: Executar o roteiro e registrar os resultados**

Rodar os passos 1–6 no ambiente real (servidor + Pi). Colar no runbook (seção "Execução"): o comando de sync usado, a versão publicada, a confirmação do drift fechado, o valor de CH1 lido (mA cru + engenharia), e uma evidência do dashboard (ou a query Timescale confirmando a leitura). Se algum passo falhar, registrar o erro e o diagnóstico.

- [ ] **Step 3: Commit do runbook (com a seção de execução preenchida)**

```bash
git add docs/runbooks/fase5-config-loop-e2e-hub.md
git commit -m "docs(fase5-hub): runbook E2E do laço de config em hardware (N4AIB16 CH1)"
```

---

## Encerramento do Plano B

Ao fim: o Hub real recebe config do Odoo (SFTP+MQTT), aplica e recarrega o leitor, reporta de volta (applied + heartbeat retido), o drift fecha no Odoo, e o N4AIB16 real (CH1) é lido com a config publicada — valor no dashboard. Laço de configuração fechado em hardware (grau M2).

## Self-Review (feita)
- **Cobertura da spec:** §4.3 baixar (T1), §4.1 identidade/merge (T2), §4.2 AgenteControle (T3), §4.4 reload+wiring (T4), §5 extensão servidor (T5), §7/§8.2 E2E (T6). Contratos §6 (tópicos, +00:00, heartbeat com aplicada) cobertos em T3/T5.
- **Placeholders:** as 2 notas ("_fixtures_config.py"; main() sem teste unitário) são de fiação/reuso, não lacunas de design. O runbook T6 é operacional por natureza (execução real), não código.
- **Consistência de tipos:** `baixar(caminho_remoto, caminho_local)` (T1) usado como `sftp_baixar` em T3; `fundir/escrever_config_efetivo` (T2) usados em T3; `executar(..., reconfigurar, caminho_config)` (T4) casa com o Event de T3; `registrar_versao_aplicada(cliente, hub_code, versao, quando)` (T5) reusada por report e presença.
