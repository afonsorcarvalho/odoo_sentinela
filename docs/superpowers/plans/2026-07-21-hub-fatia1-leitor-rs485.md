# Hub — Fatia 1: Leitor RS-485 → arquivo assinado + MQTT — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer o Raspberry Pi (Hub) ler o barramento RS-485/Modbus (N4AIB16), converter para grandeza física, gravar o `.txt` diário assinado (byte-compatível com `ingestao/validador.py`) e publicar telemetria no Mosquitto local.

**Architecture:** Novo pacote `hub/` no repo `odoo_sentinela`. O contrato de formato/assinatura é extraído de `coletor_simulado/` para um pacote `contrato/` compartilhado. A leitura Modbus reusa o projeto `modbus-connector` (git submodule em `hub/vendor/`), isolado atrás de `hub/modbus_backend.py`. Um loop lê → normaliza → grava (hash encadeado + selagem diária assinada) e publica MQTT em paralelo.

**Tech Stack:** Python 3.13, `cryptography` (EC SECP256R1), `PyYAML`, `paho-mqtt`, `pyserial` (via submodule), `pytest`. Dev venv em `.venv/` (já criado).

## Global Constraints

- **Contrato de arquivo é fonte única:** todo formato/hash/assinatura vem de `contrato/formato.py` e `contrato/identidade.py`. O Hub NUNCA reimplementa hash/assinatura.
- **Cadeia de hash reinicia a cada dia** (não atravessa dias). Seed = `sha256(cabecalho_canonico)`; cada linha = `sha256(hash_anterior + linha_sem_hash)`.
- **Assinatura:** `base64( ECDSA-SHA256( hash_final.encode() ) )` no rodapé, campo `# assinatura:`. Chave EC SECP256R1.
- **Delimitador `|`, `\n`, `\r` proibidos em identificadores** (`contrato.formato.validar_identificador`).
- **Modbus só via `modbus-connector` (pyserial-only), nunca `pymodbus`.**
- **Falha de MQTT nunca derruba o loop nem impede a gravação do arquivo** (arquivo = fonte de verdade).
- **Tópico de telemetria v1:** `sentinela/telemetria/{hub_id}/{coletor_id}/{sensor_id}`, JSON `{timestamp, tipo_medida, valor, unidade, area_id, status}`, QoS 0, não-retido.
- **Timezone:** timestamps tz-aware no offset da config; string da linha = `datetime.isoformat(timespec='seconds')`.
- **Todos os comandos rodam com o venv ativo:** `cd /home/fitadigital/odoo_sentinela && . .venv/bin/activate`.

---

## File Structure

```
contrato/                       # NOVO — contrato compartilhado (extraído de coletor_simulado)
  __init__.py
  formato.py                    # movido de coletor_simulado/formato.py
  identidade.py                 # movido de coletor_simulado/identidade.py
  tests/
    __init__.py
    test_formato.py             # movido
    test_identidade.py          # movido
hub/                            # NOVO — software do Hub
  __init__.py
  vendor/modbus-connector/      # git submodule
  modbus_backend.py             # bootstrap do sys.path + fábrica de driver + re-export
  config.py                     # carrega/valida YAML → dataclasses
  assinador.py                  # Assinador (Protocol) + AssinadorSoftware
  arquivo_diario.py             # escritor do .txt diário (append/hash/selagem/recuperação)
  leitor.py                     # loop de leitura Modbus → leituras normalizadas
  publicador_mqtt.py            # publica leitura no broker local
  main.py                       # fia tudo, loop, sinais
  config.example.yaml
  requirements.txt
  tests/
    __init__.py
    test_config.py
    test_assinador.py
    test_arquivo_diario.py
    test_leitor.py
    test_publicador_mqtt.py
    test_main.py
    test_aceitacao.py
```

---

### Task 1: Extrair o contrato compartilhado `contrato/`

Move `formato.py` e `identidade.py` de `coletor_simulado/` para um pacote `contrato/` novo, importado por `coletor_simulado`, `ingestao` e (depois) `hub`. Sem mudança de comportamento — o teste é a suíte existente continuar verde.

**Files:**
- Create: `contrato/__init__.py`, `contrato/tests/__init__.py`
- Move: `coletor_simulado/formato.py` → `contrato/formato.py`
- Move: `coletor_simulado/identidade.py` → `contrato/identidade.py`
- Move: `coletor_simulado/tests/test_formato.py` → `contrato/tests/test_formato.py`
- Move: `coletor_simulado/tests/test_identidade.py` → `contrato/tests/test_identidade.py`
- Modify: `coletor_simulado/gerador.py:7`, `coletor_simulado/tests/test_gerador.py:4`, `ingestao/tests/test_validador.py:4`

**Interfaces:**
- Produces: `contrato.formato` (funções `validar_identificador`, `montar_cabecalho(tipo_arquivo, coletor_id, hub_id, pubkey_fingerprint, data_referencia, timezone_offset, firmware_version)`, `hash_seed(cabecalho_canonico)`, `hash_linha(hash_anterior, linha_sem_hash)`, `gerar_linha_leitura(hash_anterior, seq, timestamp, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura) -> (linha, novo_hash)`, `montar_rodape(total, hash_final, assinatura_b64, campo_total)`); `contrato.identidade` (`carregar_ou_criar_chave(caminho)`, `fingerprint_publica(chave)`, `assinar(chave, dado_bytes) -> bytes`, `verificar_assinatura(chave_pub, assinatura, dado_bytes)`).

- [ ] **Step 1: Mover os arquivos e criar os `__init__.py`**

```bash
cd /home/fitadigital/odoo_sentinela && . .venv/bin/activate
mkdir -p contrato/tests
git mv coletor_simulado/formato.py contrato/formato.py
git mv coletor_simulado/identidade.py contrato/identidade.py
git mv coletor_simulado/tests/test_formato.py contrato/tests/test_formato.py
git mv coletor_simulado/tests/test_identidade.py contrato/tests/test_identidade.py
touch contrato/__init__.py contrato/tests/__init__.py
git add contrato/__init__.py contrato/tests/__init__.py
```

- [ ] **Step 2: Atualizar os imports**

Em `coletor_simulado/gerador.py` linha 7, trocar:
```python
from . import formato, identidade
```
por:
```python
from contrato import formato, identidade
```

Em `coletor_simulado/tests/test_gerador.py` linha 4, trocar:
```python
from coletor_simulado import gerador, identidade
```
por:
```python
from coletor_simulado import gerador
from contrato import identidade
```

Em `contrato/tests/test_formato.py` linha 3, trocar:
```python
from coletor_simulado import formato
```
por:
```python
from contrato import formato
```

Em `contrato/tests/test_identidade.py` linha 5, trocar:
```python
from coletor_simulado import identidade
```
por:
```python
from contrato import identidade
```

Em `ingestao/tests/test_validador.py` linha 4, trocar:
```python
from coletor_simulado import identidade as identidade_simulado
```
por:
```python
from contrato import identidade as identidade_simulado
```

- [ ] **Step 3: Rodar as suítes afetadas — devem passar sem mudança de comportamento**

Run: `python -m pytest contrato/tests coletor_simulado/tests ingestao/tests/test_validador.py -q`
Expected: PASS (14 + 6 = 20 testes verdes; nenhum import quebrado)

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(contrato): extrai formato+identidade de coletor_simulado para pacote compartilhado"
```

---

### Task 2: Submodule do `modbus-connector` + `hub/modbus_backend.py`

Adiciona a lib como submodule e cria a camada de isolamento que o resto do Hub usa. Toda a dependência do vendor (sys.path, nomes de driver) fica confinada aqui — permite mockar o Modbus nos testes das outras tasks.

**Files:**
- Create: `hub/__init__.py`, `hub/tests/__init__.py`, `hub/modbus_backend.py`, `hub/tests/test_modbus_backend.py`, `hub/requirements.txt`
- Create (submodule): `hub/vendor/modbus-connector/`

**Interfaces:**
- Consumes (do vendor): `drivers.n4aib16.N4AIB16(port, baud=9600, address=1, function=4, parity="N", stopbits=1, ...)` com `.read_channels(maps=None, samples=1, ...)` e `.close()`; `common.scaling.MapSpec(channels:set, in_min, in_max, out_min, out_max, unit="", clamp=False)`.
- Produces: `hub.modbus_backend.MapSpec` (re-export), `hub.modbus_backend.criar_driver(driver_nome, porta, baud, paridade, stopbits, endereco) -> objeto com read_channels()/close()` (raise `ValueError` para driver desconhecido).

- [ ] **Step 1: Adicionar o submodule e o requirements**

```bash
cd /home/fitadigital/odoo_sentinela && . .venv/bin/activate
git submodule add https://github.com/afonsorcarvalho/modbus-connector.git hub/vendor/modbus-connector
mkdir -p hub/tests
touch hub/__init__.py hub/tests/__init__.py
printf 'cryptography>=42\nPyYAML>=6\npaho-mqtt>=1.6\npyserial>=3.5\npytest>=8\n' > hub/requirements.txt
git add hub/requirements.txt
```

- [ ] **Step 2: Escrever o teste falho**

Create `hub/tests/test_modbus_backend.py`:
```python
import pytest

from hub import modbus_backend


def test_map_spec_reexportado_aplica_escala():
    spec = modbus_backend.MapSpec(channels={1}, in_min=4, in_max=20, out_min=0, out_max=100)
    assert spec.apply(4) == 0
    assert spec.apply(20) == 100
    assert spec.apply(12) == 50


def test_criar_driver_desconhecido_falha():
    with pytest.raises(ValueError):
        modbus_backend.criar_driver("inexistente", "/dev/null", 9600, "N", 1, 1)
```

- [ ] **Step 3: Rodar — deve falhar**

Run: `python -m pytest hub/tests/test_modbus_backend.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'hub.modbus_backend'`)

- [ ] **Step 4: Implementar `hub/modbus_backend.py`**

```python
"""Isolamento do projeto modbus-connector (vendored como submodule).

Toda a dependência do vendor (manipulação de sys.path, nomes de driver)
fica confinada aqui — o resto do Hub importa daqui e mocka daqui nos testes.
"""
import os
import sys

_VENDOR = os.path.join(os.path.dirname(__file__), "vendor", "modbus-connector")
if _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)

from common.scaling import MapSpec  # noqa: E402  (re-export)

_PARIDADE = {"N": "N", "E": "E", "O": "O"}


def criar_driver(driver_nome, porta, baud, paridade, stopbits, endereco):
    """Instancia o driver do dispositivo. Raise ValueError se desconhecido."""
    if driver_nome == "n4aib16":
        from drivers.n4aib16 import N4AIB16
        return N4AIB16(
            port=porta, baud=baud, address=endereco,
            parity=_PARIDADE.get(paridade, "N"), stopbits=stopbits,
        )
    raise ValueError(f"driver Modbus desconhecido: {driver_nome!r}")
```

- [ ] **Step 5: Rodar — deve passar**

Run: `python -m pytest hub/tests/test_modbus_backend.py -q`
Expected: PASS (2 testes)

- [ ] **Step 6: Commit**

```bash
git add .gitmodules hub/
git commit -m "feat(hub): submodule modbus-connector + modbus_backend (isolamento do vendor)"
```

---

### Task 3: `hub/config.py` — carregar e validar a config YAML

**Files:**
- Create: `hub/config.py`, `hub/config.example.yaml`, `hub/tests/test_config.py`

**Interfaces:**
- Consumes: `contrato.formato.validar_identificador(valor)` (raise `ValueError`).
- Produces: dataclasses `CanalConfig(ch:int, sensor_id, area_id, tipo_medida, unidade, protocolo_origem, map_in:tuple, map_out:tuple, filtro:dict|None)`, `DispositivoConfig(endereco:int, driver:str, canais:list)`, `BarramentoConfig(porta, baud, paridade, stop_bits, dispositivos:list)`, `HubConfig(hub_id, coletor_id, firmware_version, timezone_offset, intervalo_leitura_s, caminho_chave, caminho_dados, mqtt_host, mqtt_port, barramentos:list)`; função `carregar_config(caminho) -> HubConfig` (raise `ValueError` em config inválida).

- [ ] **Step 1: Escrever o teste falho**

Create `hub/tests/test_config.py`:
```python
import textwrap

import pytest

from hub import config


def _escrever(tmp_path, texto):
    caminho = tmp_path / "config.yaml"
    caminho.write_text(textwrap.dedent(texto))
    return caminho


VALIDA = """
    hub_id: HUB-0001
    coletor_id: COL-RS485-BUS0
    firmware_version: 0.1.0
    timezone_offset: "-03:00"
    intervalo_leitura_s: 60
    caminho_chave: /tmp/coletor.pem
    caminho_dados: /tmp/dados
    mqtt: {host: localhost, port: 1883}
    barramentos:
      - porta: /dev/ttyUSB0
        baud: 9600
        paridade: N
        stop_bits: 1
        dispositivos:
          - endereco: 1
            driver: n4aib16
            canais:
              - ch: 1
                sensor_id: SNR-EXP-TEMP-01
                area_id: AREA-EXPURGO
                tipo_medida: temperatura
                unidade: C
                protocolo_origem: 4-20ma
                map: {in: [4, 20], out: [-50, 150]}
"""


def test_carrega_config_valida(tmp_path):
    cfg = config.carregar_config(_escrever(tmp_path, VALIDA))
    assert cfg.hub_id == "HUB-0001"
    assert cfg.mqtt_port == 1883
    canal = cfg.barramentos[0].dispositivos[0].canais[0]
    assert canal.sensor_id == "SNR-EXP-TEMP-01"
    assert canal.map_in == (4.0, 20.0)
    assert canal.map_out == (-50.0, 150.0)


def test_rejeita_identificador_com_pipe(tmp_path):
    ruim = VALIDA.replace("SNR-EXP-TEMP-01", "SNR|RUIM")
    with pytest.raises(ValueError):
        config.carregar_config(_escrever(tmp_path, ruim))


def test_rejeita_map_com_tamanho_errado(tmp_path):
    ruim = VALIDA.replace("out: [-50, 150]", "out: [-50, 150, 9]")
    with pytest.raises(ValueError):
        config.carregar_config(_escrever(tmp_path, ruim))
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `python -m pytest hub/tests/test_config.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'hub.config'`)

- [ ] **Step 3: Implementar `hub/config.py`**

```python
"""Carrega e valida a config local do Hub (YAML) em dataclasses tipadas."""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from contrato.formato import validar_identificador


@dataclass
class CanalConfig:
    ch: int
    sensor_id: str
    area_id: str
    tipo_medida: str
    unidade: str
    protocolo_origem: str
    map_in: tuple
    map_out: tuple
    filtro: dict = None


@dataclass
class DispositivoConfig:
    endereco: int
    driver: str
    canais: list = field(default_factory=list)


@dataclass
class BarramentoConfig:
    porta: str
    baud: int
    paridade: str
    stop_bits: int
    dispositivos: list = field(default_factory=list)


@dataclass
class HubConfig:
    hub_id: str
    coletor_id: str
    firmware_version: str
    timezone_offset: str
    intervalo_leitura_s: int
    caminho_chave: str
    caminho_dados: str
    mqtt_host: str
    mqtt_port: int
    barramentos: list = field(default_factory=list)


def _par(lista, nome):
    if not isinstance(lista, list) or len(lista) != 2:
        raise ValueError(f"'{nome}' deve ter exatamente 2 elementos, veio {lista!r}")
    return (float(lista[0]), float(lista[1]))


def _canal(bruto):
    for campo in ("sensor_id", "area_id"):
        validar_identificador(str(bruto[campo]))
    mapa = bruto["map"]
    return CanalConfig(
        ch=int(bruto["ch"]),
        sensor_id=bruto["sensor_id"],
        area_id=bruto["area_id"],
        tipo_medida=bruto["tipo_medida"],
        unidade=bruto["unidade"],
        protocolo_origem=bruto.get("protocolo_origem", "4-20ma"),
        map_in=_par(mapa["in"], "map.in"),
        map_out=_par(mapa["out"], "map.out"),
        filtro=bruto.get("filtro"),
    )


def carregar_config(caminho):
    dados = yaml.safe_load(Path(caminho).read_text())
    for campo in ("hub_id", "coletor_id"):
        validar_identificador(str(dados[campo]))
    barramentos = []
    for bus in dados["barramentos"]:
        dispositivos = [
            DispositivoConfig(
                endereco=int(d["endereco"]),
                driver=d["driver"],
                canais=[_canal(c) for c in d["canais"]],
            )
            for d in bus["dispositivos"]
        ]
        barramentos.append(BarramentoConfig(
            porta=bus["porta"], baud=int(bus["baud"]),
            paridade=bus.get("paridade", "N"), stop_bits=int(bus.get("stop_bits", 1)),
            dispositivos=dispositivos,
        ))
    mqtt = dados.get("mqtt", {})
    return HubConfig(
        hub_id=dados["hub_id"], coletor_id=dados["coletor_id"],
        firmware_version=dados["firmware_version"], timezone_offset=dados["timezone_offset"],
        intervalo_leitura_s=int(dados["intervalo_leitura_s"]),
        caminho_chave=dados["caminho_chave"], caminho_dados=dados["caminho_dados"],
        mqtt_host=mqtt.get("host", "localhost"), mqtt_port=int(mqtt.get("port", 1883)),
        barramentos=barramentos,
    )
```

- [ ] **Step 4: Rodar — deve passar**

Run: `python -m pytest hub/tests/test_config.py -q`
Expected: PASS (3 testes)

- [ ] **Step 5: Criar `hub/config.example.yaml`**

```yaml
hub_id: HUB-0001A2F3
coletor_id: COL-RS485-BUS0        # "coletor lógico" deste barramento RS-485
firmware_version: 0.1.0
timezone_offset: "-03:00"
intervalo_leitura_s: 60            # default; use 5 em teste
caminho_chave: ~/sentinela-hub/chaves/coletor.pem
caminho_dados: ~/sentinela-hub/dados
mqtt:
  host: localhost
  port: 1883
barramentos:
  - porta: /dev/ttyUSB0
    baud: 9600
    paridade: N
    stop_bits: 1
    dispositivos:
      - endereco: 1
        driver: n4aib16
        canais:
          - ch: 1
            sensor_id: SNR-EXP-TEMP-01
            area_id: AREA-EXPURGO
            tipo_medida: temperatura
            unidade: C
            protocolo_origem: 4-20ma
            map: {in: [4, 20], out: [-50, 150]}   # mA -> °C
            filtro: {tipo: ewma, alpha: 0.3}       # opcional
```

- [ ] **Step 6: Commit**

```bash
git add hub/config.py hub/config.example.yaml hub/tests/test_config.py
git commit -m "feat(hub): config.py — carga e validação da config YAML local"
```

---

### Task 4: `hub/assinador.py` — interface de assinatura + implementação software

**Files:**
- Create: `hub/assinador.py`, `hub/tests/test_assinador.py`

**Interfaces:**
- Consumes: `contrato.identidade.carregar_ou_criar_chave(caminho)`, `.fingerprint_publica(chave)`, `.assinar(chave, dado_bytes)`, `.verificar_assinatura(chave_pub, assinatura, dado_bytes)`.
- Produces: `hub.assinador.Assinador` (Protocol com `fingerprint() -> str` e `assinar(dado: bytes) -> bytes`); `hub.assinador.AssinadorSoftware(caminho_chave)` implementando o Protocol e expondo `chave_publica_pem() -> str`.

- [ ] **Step 1: Escrever o teste falho**

Create `hub/tests/test_assinador.py`:
```python
from contrato import identidade
from hub.assinador import AssinadorSoftware


def test_assina_e_verifica(tmp_path):
    ass = AssinadorSoftware(tmp_path / "k.pem")
    dado = b"hash-final-de-teste"
    assinatura = ass.assinar(dado)
    chave_pub = identidade.carregar_ou_criar_chave(tmp_path / "k.pem").public_key()
    identidade.verificar_assinatura(chave_pub, assinatura, dado)  # não levanta = ok


def test_fingerprint_estavel(tmp_path):
    ass = AssinadorSoftware(tmp_path / "k.pem")
    assert ass.fingerprint() == ass.fingerprint()
    assert ":" in ass.fingerprint()


def test_expoe_chave_publica_pem(tmp_path):
    ass = AssinadorSoftware(tmp_path / "k.pem")
    pem = ass.chave_publica_pem()
    assert pem.startswith("-----BEGIN PUBLIC KEY-----")
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `python -m pytest hub/tests/test_assinador.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'hub.assinador'`)

- [ ] **Step 3: Implementar `hub/assinador.py`**

```python
"""Assinatura do arquivo diário. Interface + implementação em software (EC).

Ponto de extensão: uma implementação ATECC608 futura só precisa satisfazer
o mesmo Protocol, sem tocar o resto do Hub.
"""
from typing import Protocol

from cryptography.hazmat.primitives import serialization

from contrato import identidade


class Assinador(Protocol):
    def fingerprint(self) -> str: ...
    def assinar(self, dado: bytes) -> bytes: ...


class AssinadorSoftware:
    def __init__(self, caminho_chave):
        self._chave = identidade.carregar_ou_criar_chave(caminho_chave)

    def fingerprint(self) -> str:
        return identidade.fingerprint_publica(self._chave)

    def assinar(self, dado: bytes) -> bytes:
        return identidade.assinar(self._chave, dado)

    def chave_publica_pem(self) -> str:
        return self._chave.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
```

- [ ] **Step 4: Rodar — deve passar**

Run: `python -m pytest hub/tests/test_assinador.py -q`
Expected: PASS (3 testes)

- [ ] **Step 5: Commit**

```bash
git add hub/assinador.py hub/tests/test_assinador.py
git commit -m "feat(hub): assinador.py — interface Assinador + AssinadorSoftware (EC)"
```

---

### Task 5: `hub/arquivo_diario.py` — escritor do `.txt` diário

Gera o arquivo diário no formato congelado: escreve cabeçalho ao abrir o dia, anexa uma linha por leitura com hash encadeado, e **sela** (rodapé + assinatura) na virada de dia ou no encerramento. Recupera arquivos de dias passados não-selados no boot.

**Files:**
- Create: `hub/arquivo_diario.py`, `hub/tests/test_arquivo_diario.py`

**Interfaces:**
- Consumes: `contrato.formato` (`montar_cabecalho`, `hash_seed`, `gerar_linha_leitura`, `montar_rodape`); `hub.assinador.Assinador`.
- Consumes (leitura normalizada): dict `{"timestamp": datetime (tz-aware), "sensor_id", "area_id", "tipo_medida", "valor": float, "unidade", "protocolo_origem", "status_leitura"}`.
- Produces: `hub.arquivo_diario.ArquivoDiario(coletor_id, hub_id, firmware_version, timezone_offset, caminho_dados, assinador)` com `registrar(leitura)`, `selar(data_referencia=None)`, `recuperar_pendentes(hoje: date)`, `caminho(data_referencia) -> Path`; função módulo `reconstruir_estado(texto) -> (hash_atual, proximo_seq)`.

- [ ] **Step 1: Escrever o teste falho**

Create `hub/tests/test_arquivo_diario.py`:
```python
from datetime import date, datetime, timedelta, timezone

from hub.arquivo_diario import ArquivoDiario
from hub.assinador import AssinadorSoftware

TZ = timezone(timedelta(hours=-3))


def _leitura(dt, valor=19.8, sensor="SNR-EXP-TEMP-01"):
    return {
        "timestamp": dt, "sensor_id": sensor, "area_id": "AREA-EXPURGO",
        "tipo_medida": "temperatura", "valor": valor, "unidade": "C",
        "protocolo_origem": "4-20ma", "status_leitura": "ok",
    }


def _fazer(tmp_path):
    ass = AssinadorSoftware(tmp_path / "k.pem")
    arq = ArquivoDiario("COL-RS485-BUS0", "HUB-0001", "0.1.0", "-03:00",
                        tmp_path / "dados", ass)
    return arq, ass


def test_registrar_cria_cabecalho_e_linha(tmp_path):
    arq, _ = _fazer(tmp_path)
    dt = datetime(2026, 7, 21, 0, 1, tzinfo=TZ)
    arq.registrar(_leitura(dt))
    texto = arq.caminho("2026-07-21").read_text()
    assert "# coletor_id: COL-RS485-BUS0" in texto
    assert "SNR-EXP-TEMP-01|AREA-EXPURGO|temperatura|19.8|C|4-20ma|ok|" in texto


def test_selar_adiciona_rodape_com_assinatura(tmp_path):
    arq, _ = _fazer(tmp_path)
    dt = datetime(2026, 7, 21, 0, 1, tzinfo=TZ)
    arq.registrar(_leitura(dt))
    arq.selar("2026-07-21")
    texto = arq.caminho("2026-07-21").read_text()
    assert "# hash_final: " in texto
    assert "# assinatura: " in texto


def test_virada_de_dia_sela_o_anterior(tmp_path):
    arq, _ = _fazer(tmp_path)
    arq.registrar(_leitura(datetime(2026, 7, 21, 23, 59, tzinfo=TZ)))
    arq.registrar(_leitura(datetime(2026, 7, 22, 0, 1, tzinfo=TZ)))
    ontem = arq.caminho("2026-07-21").read_text()
    hoje = arq.caminho("2026-07-22").read_text()
    assert "# assinatura: " in ontem          # dia anterior foi selado
    assert "# assinatura: " not in hoje        # dia corrente ainda aberto


def test_recuperar_pendentes_sela_dia_passado(tmp_path):
    arq, _ = _fazer(tmp_path)
    arq.registrar(_leitura(datetime(2026, 7, 20, 10, 0, tzinfo=TZ)))
    # simula crash: não selou. Nova instância recupera.
    arq2, _ = _fazer(tmp_path)
    arq2.recuperar_pendentes(date(2026, 7, 21))
    texto = arq2.caminho("2026-07-20").read_text()
    assert "# assinatura: " in texto
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `python -m pytest hub/tests/test_arquivo_diario.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'hub.arquivo_diario'`)

- [ ] **Step 3: Implementar `hub/arquivo_diario.py`**

```python
"""Escritor do arquivo .txt diário de leituras, no formato congelado.

Uma linha por leitura, hash encadeado interno ao dia; selagem diária assina
o hash_final. Cadeia reinicia a cada dia. Recupera no boot dias passados que
ficaram sem rodapé (crash antes de selar).
"""
import base64
import glob
import os
from datetime import date
from pathlib import Path

from contrato import formato


def reconstruir_estado(texto):
    """A partir do conteúdo de um arquivo (cabeçalho + N linhas, sem rodapé),
    devolve (hash_atual, proximo_seq) — o estado de onde continuar/selar."""
    linhas = [l for l in texto.split("\n") if l != ""]
    cabecalho = [l for l in linhas if l.startswith("#")]
    corpo = [l for l in linhas if not l.startswith("#")]
    hash_atual = formato.hash_seed("\n".join(cabecalho) + "\n")
    for linha in corpo:
        sem_hash = linha.rsplit("|", 1)[0]
        hash_atual = formato.hash_linha(hash_atual, sem_hash)
    return hash_atual, len(corpo) + 1


def _esta_selado(caminho):
    return caminho.exists() and "\n# assinatura:" in caminho.read_text()


class ArquivoDiario:
    def __init__(self, coletor_id, hub_id, firmware_version, timezone_offset,
                 caminho_dados, assinador):
        self._coletor_id = coletor_id
        self._hub_id = hub_id
        self._firmware = firmware_version
        self._tz_offset = timezone_offset
        self._dir = Path(caminho_dados).expanduser() / coletor_id
        self._assinador = assinador
        self._data_atual = None
        self._hash = None
        self._seq = 1

    def caminho(self, data_referencia):
        return self._dir / f"{data_referencia}_leituras.txt"

    def _abrir(self, data_referencia):
        self._dir.mkdir(parents=True, exist_ok=True)
        caminho = self.caminho(data_referencia)
        if caminho.exists():                       # retoma arquivo do dia corrente
            self._hash, self._seq = reconstruir_estado(caminho.read_text())
        else:
            cabecalho = formato.montar_cabecalho(
                "leituras", self._coletor_id, self._hub_id,
                self._assinador.fingerprint(), data_referencia,
                self._tz_offset, self._firmware,
            )
            caminho.write_text(cabecalho)
            self._hash = formato.hash_seed(cabecalho)
            self._seq = 1
        self._data_atual = data_referencia

    def registrar(self, leitura):
        data_referencia = leitura["timestamp"].date().isoformat()
        if self._data_atual is not None and data_referencia != self._data_atual:
            self.selar(self._data_atual)
            self._data_atual = None
        if self._data_atual is None:
            self._abrir(data_referencia)
        ts = leitura["timestamp"].isoformat(timespec="seconds")
        linha, self._hash = formato.gerar_linha_leitura(
            self._hash, self._seq, ts, leitura["sensor_id"], leitura["area_id"],
            leitura["tipo_medida"], leitura["valor"], leitura["unidade"],
            leitura["protocolo_origem"], leitura["status_leitura"],
        )
        with self.caminho(data_referencia).open("a") as fh:
            fh.write(linha + "\n")
        self._seq += 1

    def selar(self, data_referencia=None):
        data_referencia = data_referencia or self._data_atual
        if data_referencia is None:
            return
        caminho = self.caminho(data_referencia)
        if _esta_selado(caminho) or not caminho.exists():
            return
        hash_final, proximo_seq = reconstruir_estado(caminho.read_text())
        assinatura = base64.b64encode(self._assinador.assinar(hash_final.encode())).decode()
        rodape = formato.montar_rodape(proximo_seq - 1, hash_final, assinatura, "total_linhas")
        with caminho.open("a") as fh:
            fh.write(rodape)

    def recuperar_pendentes(self, hoje: date):
        for nome in glob.glob(str(self._dir / "*_leituras.txt")):
            data_str = os.path.basename(nome).replace("_leituras.txt", "")
            if date.fromisoformat(data_str) < hoje and not _esta_selado(Path(nome)):
                self.selar(data_str)
```

- [ ] **Step 4: Rodar — deve passar**

Run: `python -m pytest hub/tests/test_arquivo_diario.py -q`
Expected: PASS (4 testes)

- [ ] **Step 5: Commit**

```bash
git add hub/arquivo_diario.py hub/tests/test_arquivo_diario.py
git commit -m "feat(hub): arquivo_diario.py — escrita/selagem/recuperação do .txt diário"
```

---

### Task 6: `hub/leitor.py` — loop de leitura Modbus → leituras normalizadas

Lê cada dispositivo do barramento via `modbus_backend`, aplica escala (map) e filtro opcional, e produz leituras normalizadas. Dispositivo que não responde vira `sensor_offline` (não derruba a varredura).

**Files:**
- Create: `hub/leitor.py`, `hub/tests/test_leitor.py`

**Interfaces:**
- Consumes: `hub.config.HubConfig`; `hub.modbus_backend.criar_driver(...)` e `MapSpec`; leitura do driver: `read_channels(maps=[MapSpec]) -> list[{"channel", "value", "unit", ...}]` (raise `RuntimeError` se offline).
- Produces: `hub.leitor.Leitor(config, backend=modbus_backend)` com `ler_todos(agora: datetime) -> list[dict]` (leituras normalizadas, mesmo shape que `arquivo_diario` consome) e `fechar()`.

- [ ] **Step 1: Escrever o teste falho**

Create `hub/tests/test_leitor.py`:
```python
import textwrap
from datetime import datetime, timedelta, timezone

from hub import config
from hub.leitor import Leitor

TZ = timezone(timedelta(hours=-3))

CFG = """
    hub_id: HUB-0001
    coletor_id: COL-RS485-BUS0
    firmware_version: 0.1.0
    timezone_offset: "-03:00"
    intervalo_leitura_s: 60
    caminho_chave: /tmp/coletor.pem
    caminho_dados: /tmp/dados
    mqtt: {host: localhost, port: 1883}
    barramentos:
      - porta: /dev/ttyUSB0
        baud: 9600
        paridade: N
        stop_bits: 1
        dispositivos:
          - endereco: 1
            driver: n4aib16
            canais:
              - ch: 1
                sensor_id: SNR-EXP-TEMP-01
                area_id: AREA-EXPURGO
                tipo_medida: temperatura
                unidade: C
                protocolo_origem: 4-20ma
                map: {in: [4, 20], out: [0, 100]}
"""


class _DriverFake:
    def __init__(self, valores=None, erro=False):
        self._valores = valores or [{"channel": 1, "value": 50.0, "unit": "C"}]
        self._erro = erro
    def read_channels(self, maps=None):
        if self._erro:
            raise RuntimeError("sem resposta")
        return self._valores
    def close(self):
        pass


class _BackendFake:
    def __init__(self, driver):
        self._driver = driver
        from hub.modbus_backend import MapSpec
        self.MapSpec = MapSpec
    def criar_driver(self, *a, **k):
        return self._driver


def _cfg(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(textwrap.dedent(CFG))
    return config.carregar_config(p)


def test_ler_todos_normaliza(tmp_path):
    leitor = Leitor(_cfg(tmp_path), backend=_BackendFake(_DriverFake()))
    agora = datetime(2026, 7, 21, 0, 1, tzinfo=TZ)
    leituras = leitor.ler_todos(agora)
    assert len(leituras) == 1
    r = leituras[0]
    assert r["sensor_id"] == "SNR-EXP-TEMP-01"
    assert r["valor"] == 50.0
    assert r["status_leitura"] == "ok"
    assert r["timestamp"] == agora


def test_dispositivo_offline_vira_sensor_offline(tmp_path):
    leitor = Leitor(_cfg(tmp_path), backend=_BackendFake(_DriverFake(erro=True)))
    leituras = leitor.ler_todos(datetime(2026, 7, 21, 0, 1, tzinfo=TZ))
    assert leituras[0]["status_leitura"] == "sensor_offline"
    assert leituras[0]["valor"] == 0.0
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `python -m pytest hub/tests/test_leitor.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'hub.leitor'`)

- [ ] **Step 3: Implementar `hub/leitor.py`**

```python
"""Loop de varredura Modbus: lê dispositivos, escala (map) e normaliza.

Uma instância de driver por dispositivo configurado. Dispositivo que não
responde marca todos os seus canais como sensor_offline (varredura continua).
"""
from hub import modbus_backend as _backend_padrao


class _DispositivoLigado:
    def __init__(self, driver, canais):
        self.driver = driver
        self.canais = canais  # list[CanalConfig]


class Leitor:
    def __init__(self, config, backend=_backend_padrao):
        self._config = config
        self._backend = backend
        self._dispositivos = []
        for bus in config.barramentos:
            for disp in bus.dispositivos:
                driver = backend.criar_driver(
                    disp.driver, bus.porta, bus.baud, bus.paridade, bus.stop_bits, disp.endereco,
                )
                self._dispositivos.append(_DispositivoLigado(driver, disp.canais))

    def _specs(self, canais):
        return [
            self._backend.MapSpec(
                channels={c.ch}, in_min=c.map_in[0], in_max=c.map_in[1],
                out_min=c.map_out[0], out_max=c.map_out[1], unit=c.unidade,
            )
            for c in canais
        ]

    def _normalizar(self, canal, valor, status, agora):
        return {
            "timestamp": agora, "sensor_id": canal.sensor_id, "area_id": canal.area_id,
            "tipo_medida": canal.tipo_medida, "valor": valor, "unidade": canal.unidade,
            "protocolo_origem": canal.protocolo_origem, "status_leitura": status,
        }

    def ler_todos(self, agora):
        leituras = []
        for disp in self._dispositivos:
            try:
                lidos = disp.driver.read_channels(maps=self._specs(disp.canais))
                por_canal = {e["channel"]: e for e in lidos}
                for canal in disp.canais:
                    entrada = por_canal.get(canal.ch)
                    if entrada is None:
                        leituras.append(self._normalizar(canal, 0.0, "erro_leitura", agora))
                    else:
                        leituras.append(self._normalizar(canal, float(entrada["value"]), "ok", agora))
            except RuntimeError:
                for canal in disp.canais:
                    leituras.append(self._normalizar(canal, 0.0, "sensor_offline", agora))
        return leituras

    def fechar(self):
        for disp in self._dispositivos:
            try:
                disp.driver.close()
            except Exception:
                pass
```

- [ ] **Step 4: Rodar — deve passar**

Run: `python -m pytest hub/tests/test_leitor.py -q`
Expected: PASS (2 testes)

- [ ] **Step 5: Commit**

```bash
git add hub/leitor.py hub/tests/test_leitor.py
git commit -m "feat(hub): leitor.py — varredura Modbus e normalização de leitura"
```

---

### Task 7: `hub/publicador_mqtt.py` — publica telemetria no broker local

**Files:**
- Create: `hub/publicador_mqtt.py`, `hub/tests/test_publicador_mqtt.py`

**Interfaces:**
- Consumes: leitura normalizada (dict); `paho.mqtt.client.Client` (injetável).
- Produces: `hub.publicador_mqtt.PublicadorMqtt(host, port, client=None)` com `conectar()`, `publicar(hub_id, coletor_id, leitura) -> str|None` (retorna o tópico publicado, ou None se falhou), `fechar()`.

- [ ] **Step 1: Escrever o teste falho**

Create `hub/tests/test_publicador_mqtt.py`:
```python
import json
from datetime import datetime, timedelta, timezone

from hub.publicador_mqtt import PublicadorMqtt

TZ = timezone(timedelta(hours=-3))


class _ClientFake:
    def __init__(self):
        self.publicados = []
        self.conectado = False
    def connect(self, host, port):
        self.conectado = True
    def publish(self, topico, payload, qos=0):
        self.publicados.append((topico, payload, qos))
    def disconnect(self):
        pass


def _leitura():
    return {
        "timestamp": datetime(2026, 7, 21, 0, 1, tzinfo=TZ), "sensor_id": "SNR-EXP-TEMP-01",
        "area_id": "AREA-EXPURGO", "tipo_medida": "temperatura", "valor": 19.8,
        "unidade": "C", "protocolo_origem": "4-20ma", "status_leitura": "ok",
    }


def test_publica_no_topico_e_payload_corretos():
    cli = _ClientFake()
    pub = PublicadorMqtt("localhost", 1883, client=cli)
    pub.conectar()
    topico = pub.publicar("HUB-0001", "COL-RS485-BUS0", _leitura())
    assert topico == "sentinela/telemetria/HUB-0001/COL-RS485-BUS0/SNR-EXP-TEMP-01"
    (t, payload, qos) = cli.publicados[0]
    dados = json.loads(payload)
    assert dados["valor"] == 19.8
    assert dados["status"] == "ok"
    assert dados["timestamp"] == "2026-07-21T00:01:00-03:00"


def test_falha_de_publish_nao_propaga():
    class Explode(_ClientFake):
        def publish(self, *a, **k):
            raise OSError("broker caiu")
    pub = PublicadorMqtt("localhost", 1883, client=Explode())
    pub.conectar()
    assert pub.publicar("HUB-0001", "COL-RS485-BUS0", _leitura()) is None  # não levanta
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `python -m pytest hub/tests/test_publicador_mqtt.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'hub.publicador_mqtt'`)

- [ ] **Step 3: Implementar `hub/publicador_mqtt.py`**

```python
"""Publica cada leitura no broker MQTT local. Nunca propaga falha de rede —
o arquivo assinado é a fonte de verdade; MQTT é conveniência de tempo real.
"""
import json


class PublicadorMqtt:
    def __init__(self, host, port, client=None):
        if client is None:
            import paho.mqtt.client as mqtt
            client = mqtt.Client()
        self._client = client
        self._host = host
        self._port = port

    def conectar(self):
        try:
            self._client.connect(self._host, self._port)
        except OSError:
            pass  # sem broker agora; publicar vira no-op resiliente

    def publicar(self, hub_id, coletor_id, leitura):
        topico = f"sentinela/telemetria/{hub_id}/{coletor_id}/{leitura['sensor_id']}"
        payload = json.dumps({
            "timestamp": leitura["timestamp"].isoformat(timespec="seconds"),
            "tipo_medida": leitura["tipo_medida"],
            "valor": leitura["valor"],
            "unidade": leitura["unidade"],
            "area_id": leitura["area_id"],
            "status": leitura["status_leitura"],
        })
        try:
            self._client.publish(topico, payload, qos=0)
            return topico
        except OSError:
            return None

    def fechar(self):
        try:
            self._client.disconnect()
        except OSError:
            pass
```

- [ ] **Step 4: Rodar — deve passar**

Run: `python -m pytest hub/tests/test_publicador_mqtt.py -q`
Expected: PASS (2 testes)

- [ ] **Step 5: Commit**

```bash
git add hub/publicador_mqtt.py hub/tests/test_publicador_mqtt.py
git commit -m "feat(hub): publicador_mqtt.py — telemetria no broker local (falha não-fatal)"
```

---

### Task 8: `hub/main.py` — orquestração do loop

Fia config → leitor → arquivo → publicador; recupera pendentes no boot; roda o loop (uma varredura por intervalo); trata SIGTERM selando o dia corrente.

**Files:**
- Create: `hub/main.py`, `hub/tests/test_main.py`

**Interfaces:**
- Consumes: `hub.config.HubConfig`, `hub.leitor.Leitor`, `hub.arquivo_diario.ArquivoDiario`, `hub.publicador_mqtt.PublicadorMqtt`.
- Produces: `hub.main.executar(config, leitor, arquivo, publicador, agora_fn, parar, max_ciclos=None)`; `hub.main.main(argv=None)`.

- [ ] **Step 1: Escrever o teste falho**

Create `hub/tests/test_main.py`:
```python
import textwrap
from datetime import datetime, timedelta, timezone
from threading import Event

from hub import config
from hub.assinador import AssinadorSoftware
from hub.arquivo_diario import ArquivoDiario
from hub import main as hub_main

TZ = timezone(timedelta(hours=-3))

CFG = """
    hub_id: HUB-0001
    coletor_id: COL-RS485-BUS0
    firmware_version: 0.1.0
    timezone_offset: "-03:00"
    intervalo_leitura_s: 0
    caminho_chave: {chave}
    caminho_dados: {dados}
    mqtt: {{host: localhost, port: 1883}}
    barramentos:
      - porta: /dev/ttyUSB0
        baud: 9600
        paridade: N
        stop_bits: 1
        dispositivos:
          - endereco: 1
            driver: n4aib16
            canais:
              - ch: 1
                sensor_id: SNR-EXP-TEMP-01
                area_id: AREA-EXPURGO
                tipo_medida: temperatura
                unidade: C
                protocolo_origem: 4-20ma
                map: {{in: [4, 20], out: [0, 100]}}
"""


class _LeitorFake:
    def ler_todos(self, agora):
        return [{
            "timestamp": agora, "sensor_id": "SNR-EXP-TEMP-01", "area_id": "AREA-EXPURGO",
            "tipo_medida": "temperatura", "valor": 42.0, "unidade": "C",
            "protocolo_origem": "4-20ma", "status_leitura": "ok",
        }]
    def fechar(self):
        pass


class _PubFake:
    def __init__(self):
        self.n = 0
    def conectar(self):
        pass
    def publicar(self, *a):
        self.n += 1
    def fechar(self):
        pass


def test_executar_grava_e_publica_e_sela_no_fim(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(textwrap.dedent(CFG).format(chave=tmp_path / "k.pem", dados=tmp_path / "dados"))
    cfg = config.carregar_config(p)
    arq = ArquivoDiario(cfg.coletor_id, cfg.hub_id, cfg.firmware_version,
                        cfg.timezone_offset, cfg.caminho_dados, AssinadorSoftware(cfg.caminho_chave))
    pub = _PubFake()
    agora = datetime(2026, 7, 21, 0, 1, tzinfo=TZ)
    hub_main.executar(cfg, _LeitorFake(), arq, pub, agora_fn=lambda: agora,
                      parar=Event(), max_ciclos=2)
    texto = arq.caminho("2026-07-21").read_text()
    assert texto.count("SNR-EXP-TEMP-01|") == 2   # 2 varreduras gravadas
    assert "# assinatura: " in texto              # selado no encerramento
    assert pub.n == 2                             # 2 publicações
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `python -m pytest hub/tests/test_main.py -q`
Expected: FAIL (`AttributeError: module 'hub.main' has no attribute 'executar'` ou ModuleNotFound)

- [ ] **Step 3: Implementar `hub/main.py`**

```python
"""Ponto de entrada do software do Hub (papel de coletor RS-485).

Recupera pendentes no boot, roda o loop de varredura (grava + publica por
leitura) e sela o dia corrente ao encerrar (SIGTERM ou fim de max_ciclos).
"""
import argparse
import signal
from datetime import datetime, timedelta, timezone
from threading import Event

from hub import config as config_mod
from hub.arquivo_diario import ArquivoDiario
from hub.assinador import AssinadorSoftware
from hub.leitor import Leitor
from hub.publicador_mqtt import PublicadorMqtt


def _tz(offset):
    sinal = 1 if offset[0] == "+" else -1
    horas, minutos = int(offset[1:3]), int(offset[4:6])
    return timezone(sinal * timedelta(hours=horas, minutes=minutos))


def executar(config, leitor, arquivo, publicador, agora_fn, parar, max_ciclos=None):
    arquivo.recuperar_pendentes(agora_fn().date())
    publicador.conectar()
    ciclos = 0
    data_corrente = None
    while not parar.is_set():
        agora = agora_fn()
        data_corrente = agora.date().isoformat()
        for leitura in leitor.ler_todos(agora):
            arquivo.registrar(leitura)
            publicador.publicar(config.hub_id, config.coletor_id, leitura)
        ciclos += 1
        if max_ciclos is not None and ciclos >= max_ciclos:
            break
        parar.wait(config.intervalo_leitura_s)
    arquivo.selar(data_corrente)
    leitor.fechar()
    publicador.fechar()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Hub Sentinela — coletor RS-485")
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    cfg = config_mod.carregar_config(args.config)
    tz = _tz(cfg.timezone_offset)
    assinador = AssinadorSoftware(cfg.caminho_chave)
    arquivo = ArquivoDiario(cfg.coletor_id, cfg.hub_id, cfg.firmware_version,
                            cfg.timezone_offset, cfg.caminho_dados, assinador)
    leitor = Leitor(cfg)
    publicador = PublicadorMqtt(cfg.mqtt_host, cfg.mqtt_port)
    parar = Event()
    signal.signal(signal.SIGTERM, lambda *_: parar.set())
    signal.signal(signal.SIGINT, lambda *_: parar.set())
    executar(cfg, leitor, arquivo, publicador,
             agora_fn=lambda: datetime.now(tz), parar=parar)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Rodar — deve passar**

Run: `python -m pytest hub/tests/test_main.py -q`
Expected: PASS (1 teste)

- [ ] **Step 5: Commit**

```bash
git add hub/main.py hub/tests/test_main.py
git commit -m "feat(hub): main.py — orquestração do loop (boot/recuperação/selagem/sinais)"
```

---

### Task 9: Teste de aceitação — arquivo do Hub passa no validador da ingestão

Prova a fatia: um arquivo gerado ponta a ponta pelo Hub (com backend Modbus fake) é aceito pelo `ingestao/validador.py` (hash encadeado + assinatura). Fecha o ciclo de compatibilidade com o servidor.

**Files:**
- Create: `hub/tests/test_aceitacao.py`

**Interfaces:**
- Consumes: `hub.arquivo_diario.ArquivoDiario`, `hub.assinador.AssinadorSoftware`, `ingestao.registro_coletores.registrar_coletor(caminho, coletor_id, chave_publica_pem)`, `ingestao.validador.validar_arquivo(caminho, registro_path) -> ResultadoValidacao(status_validacao)`.

- [ ] **Step 1: Escrever o teste de aceitação**

Create `hub/tests/test_aceitacao.py`:
```python
from datetime import datetime, timedelta, timezone

from hub.arquivo_diario import ArquivoDiario
from hub.assinador import AssinadorSoftware
from ingestao import registro_coletores, validador

TZ = timezone(timedelta(hours=-3))


def _leitura(dt, valor, sensor):
    return {
        "timestamp": dt, "sensor_id": sensor, "area_id": "AREA-EXPURGO",
        "tipo_medida": "temperatura", "valor": valor, "unidade": "C",
        "protocolo_origem": "4-20ma", "status_leitura": "ok",
    }


def test_arquivo_do_hub_e_aceito_pela_ingestao(tmp_path):
    coletor_id = "COL-RS485-BUS0"
    assinador = AssinadorSoftware(tmp_path / "k.pem")
    arq = ArquivoDiario(coletor_id, "HUB-0001", "0.1.0", "-03:00", tmp_path / "dados", assinador)

    base = datetime(2026, 7, 21, 0, 1, tzinfo=TZ)
    for i in range(3):
        arq.registrar(_leitura(base + timedelta(minutes=i), 19.0 + i * 0.1, "SNR-EXP-TEMP-01"))
    arq.selar("2026-07-21")

    registro = tmp_path / "coletores_conhecidos.json"
    registro_coletores.registrar_coletor(registro, coletor_id, assinador.chave_publica_pem())

    resultado = validador.validar_arquivo(arq.caminho("2026-07-21"), registro)
    assert resultado.status_validacao == "valido", resultado.motivo_rejeicao
    assert resultado.total_linhas == 3
```

- [ ] **Step 2: Rodar — deve passar (todos os módulos já existem)**

Run: `python -m pytest hub/tests/test_aceitacao.py -q`
Expected: PASS (1 teste) — status `valido`. Se falhar com "cadeia de hash quebrada" ou "assinatura inválida", há divergência entre o formato do Hub e o `contrato` — investigar antes de prosseguir.

- [ ] **Step 3: Rodar a suíte inteira do Hub + contrato + validador**

Run: `python -m pytest hub/tests contrato/tests ingestao/tests/test_validador.py -q`
Expected: PASS (todos)

- [ ] **Step 4: Commit**

```bash
git add hub/tests/test_aceitacao.py
git commit -m "test(hub): aceitação — arquivo do Hub validado pela ingestão (hash+assinatura)"
```

---

## Validação no hardware real (manual, fora do CI — precisa do N4AIB16)

Após as 9 tasks, com o N4AIB16 no barramento USB-RS485:

1. Confirmar a porta: `ls /dev/ttyUSB*` (usuário no grupo `dialout`).
2. Copiar `hub/config.example.yaml` para `~/sentinela-hub/config.yaml`, ajustar `porta`/`endereco`/`map` conforme o transmissor real.
3. Rodar por alguns minutos com intervalo curto: editar `intervalo_leitura_s: 5` e `python -m hub.main --config ~/sentinela-hub/config.yaml`.
4. Verificar o arquivo em `~/sentinela-hub/dados/COL-RS485-BUS0/<data>_leituras.txt` crescendo; `Ctrl+C` sela o arquivo.
5. (Opcional) `mosquitto_sub -t 'sentinela/telemetria/#' -v` num terminal para ver a telemetria (requer `mosquitto`/`mosquitto-clients` instalados).
6. Validar o arquivo real com o mesmo caminho do teste de aceitação (registrar a pubkey + `validador.validar_arquivo`).

---

## Self-Review (preenchido)

**Cobertura do spec:**
- §1.1 leitor multi-barramento sobre modbus-connector → Tasks 2, 6. ✓
- §1.1 conversão 4-20mA→física (scaling) + filtro → Task 3 (map na config) + Task 6 (aplica map). Filtro EWMA per-canal fica como campo de config aceito, aplicação plena delegada (map é a transformação essencial da fatia). ✓ (limitação registrada abaixo)
- §1.1 arquivo diário assinado (hash/selagem) → Task 5. ✓
- §1.1 interface Assinador + software → Task 4. ✓
- §1.1 publish MQTT local (contrato de tópico v1) → Task 7. ✓
- §1.1 recuperação no boot → Task 5 (`recuperar_pendentes`). ✓
- §1.1 aceitação via `ingestao/validador.py` → Task 9. ✓
- §2 decisões (submodule, contrato compartilhado, config local, assinatura software) → Tasks 1, 2, 3, 4. ✓
- §3 decomposição em módulos → uma task por módulo. ✓

**Limitações conscientes (não bloqueiam a fatia, registradas):**
- **Múltiplos dispositivos no mesmo barramento serial:** cada `DispositivoConfig` instancia um driver que abre a própria serial. Dois dispositivos na mesma `porta` abririam `/dev/ttyUSB*` duas vezes — não suportado nesta fatia (hardware atual = 1 N4AIB16). Multi-**bus** (portas distintas) funciona. Compartilhar uma serial entre endereços exige refactor do driver — fora de escopo.
- **Filtro EWMA per-canal:** o campo `filtro` é carregado pela config mas a fatia aplica só o `map` (escala). Aplicação do EWMA per-canal fica para refino posterior; não afeta a validade do arquivo.
- **`status_leitura`:** a fatia emite `ok`/`sensor_offline`/`erro_leitura`. `fora_faixa_fisica` depende de limites físicos ainda não modelados na config — fora de escopo.

**Placeholder scan:** nenhum TBD/TODO; todo step de código traz o código completo. ✓
**Consistência de tipos:** `ArquivoDiario.registrar(leitura)` consome o mesmo dict que `Leitor.ler_todos` e `_LeitorFake` produzem (mesmas chaves); `PublicadorMqtt.publicar` idem; `MapSpec` (kwargs `in_min/in_max/out_min/out_max/unit`) consistente com a assinatura real de `common.scaling.MapSpec`. ✓
