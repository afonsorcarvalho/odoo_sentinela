# Contrato de driver comum via adapter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer o `leitor` do Hub consumir os drivers N4AIB16 e RS-WS-N01-2D por uma interface única (adapter), com map opcional por canal, cabeando o driver RS já existente.

**Architecture:** Um adapter fino por família no seam `hub/modbus_backend.py` expõe `ler(maps)`/`close()`; `criar_driver` devolve o adapter. O RS injeta `channel=i+1` nas entries (que só têm `name`/`register`). `leitor._specs` monta `MapSpec` só para canais com map real; canal sem map recebe o valor nativo do driver. Submódulo `modbus-connector` sobe de `c5be581` para `fc70ffb` (traz `rs_ws_n01_2d.py`, N4 inalterado).

**Tech Stack:** Python 3, pytest. Sem novas dependências. Drivers no submódulo `hub/vendor/modbus-connector` (repo git separado).

## Global Constraints

- Interface uniforme do adapter: método `ler(maps)` → `list[dict]` com chaves garantidas `channel` (int 1-based, batendo `CanalConfig.ch`), `value`, `unit`; e `close()`.
- RS: `channel = i+1` na ordem de retorno (1=umidade, 2=temperatura). N4: entries já têm `channel`, repassa.
- Map opcional: canal sem `map` → `map_in=map_out=None` → fica FORA da lista `maps` → driver preserva o `value` nativo (`channel_maps.get()` devolve None). NÃO zerar leitura por `map:[0,0]`.
- Submódulo pin de SHA `fc70ffb` (não branch). Verificado: diff `c5be581..fc70ffb` NÃO toca `drivers/n4aib16.py` nem `common/`.
- `criar_driver` do RS usa os defaults de família do driver (`function=3`), passando só `port/baud/address/parity/stopbits` — igual ao ramo N4.
- Escopo: SÓ `hub/` (submódulo, modbus_backend, leitor, config, testes). Nada de addon Odoo, serializer, frontend.
- Rodar testes: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub -q`.

## Estado atual (referência)

`hub/modbus_backend.py` `criar_driver`:
```python
def criar_driver(driver_nome, porta, baud, paridade, stopbits, endereco):
    if driver_nome == "n4aib16":
        from drivers.n4aib16 import N4AIB16
        return N4AIB16(
            port=porta, baud=baud, address=endereco,
            parity=_PARIDADE.get(paridade, "N"), stopbits=stopbits,
        )
    raise ValueError(f"driver Modbus desconhecido: {driver_nome!r}")
```

`hub/leitor.py` `ler_todos` chama `lidos = disp.driver.read_channels(maps=self._specs(disp.canais))` e `fechar` chama `disp.driver.close()`. `_specs`:
```python
def _specs(self, canais):
    return [
        self._backend.MapSpec(
            channels={c.ch}, in_min=c.map_in[0], in_max=c.map_in[1],
            out_min=c.map_out[0], out_max=c.map_out[1], unit=c.unidade,
        )
        for c in canais
    ]
```

`hub/config.py`: `CanalConfig.map_in: tuple` / `map_out: tuple` (obrigatórios); `_canal` faz `mapa = bruto["map"]` (KeyError se ausente).

---

## Task 1: Bump do submódulo modbus-connector

**Files:**
- Modify: `hub/vendor/modbus-connector` (ponteiro do submódulo: `c5be581` → `fc70ffb`)
- Test: novo `hub/tests/test_vendor_drivers.py`

**Interfaces:**
- Produces: o arquivo `drivers/rs_ws_n01_2d.py` (classe `RSWSN012D`, método `read_measurements`) passa a existir no checkout do submódulo, importável via `modbus_backend`.

- [ ] **Step 1: Escrever o teste que falha (RS driver importável)**

Criar `hub/tests/test_vendor_drivers.py`:
```python
"""Garante que o driver RS-WS-N01-2D está presente no submódulo (bump fc70ffb)."""
from hub import modbus_backend  # noqa: F401  (garante sys.path do vendor)


def test_rs_ws_n01_2d_importavel():
    from drivers.rs_ws_n01_2d import RSWSN012D
    # read_measurements é a interface que o AdaptadorRS vai consumir (Task 3).
    assert hasattr(RSWSN012D, "read_measurements")


def test_n4aib16_continua_importavel():
    from drivers.n4aib16 import N4AIB16
    assert hasattr(N4AIB16, "read_channels")
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub/tests/test_vendor_drivers.py -v`
Expected: `test_rs_ws_n01_2d_importavel` FAIL com `ModuleNotFoundError: No module named 'drivers.rs_ws_n01_2d'` (submódulo ainda em `c5be581`).

- [ ] **Step 3: Fazer o bump do submódulo**

O fetch de `origin/main` já foi feito nesta sessão; `fc70ffb` está disponível localmente. Se não estiver, refazer o fetch primeiro.
```bash
cd /home/afonso/docker/odoo_sentinela
git -C hub/vendor/modbus-connector fetch origin main    # idempotente
git -C hub/vendor/modbus-connector checkout fc70ffb
```
Confirmar que o driver existe:
```bash
ls hub/vendor/modbus-connector/drivers/rs_ws_n01_2d.py
git -C hub/vendor/modbus-connector rev-parse --short HEAD   # deve imprimir fc70ffb
```

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub/tests/test_vendor_drivers.py -v`
Expected: PASS (ambos).

- [ ] **Step 5: Rodar a suíte hub inteira (regressão do N4)**

Run: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub -q`
Expected: PASS — o N4 não mudou no range do bump, nada de leitor/config deve regredir.

- [ ] **Step 6: Commit**

O ponteiro do submódulo é rastreado no repo pai (`git add hub/vendor/modbus-connector` grava o novo SHA).
```bash
cd /home/afonso/docker/odoo_sentinela
git add hub/vendor/modbus-connector hub/tests/test_vendor_drivers.py
git commit -m "chore(hub): bump modbus-connector c5be581->fc70ffb (traz rs_ws_n01_2d)

N4AIB16 inalterado no range (diff nao toca n4aib16.py nem common/); o bump
so adiciona o driver RS-WS-N01-2D + docs. Habilita o wiring do RS no plano B.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Map opcional por canal (config + leitor._specs)

**Files:**
- Modify: `hub/config.py` (`CanalConfig`, `_canal`)
- Modify: `hub/leitor.py` (`_specs`)
- Test: `hub/tests/test_config.py`, `hub/tests/test_leitor.py`

**Interfaces:**
- Consumes: nada da Task 1.
- Produces: `CanalConfig.map_in`/`map_out` podem ser `None`. `_specs` devolve `MapSpec` só para canais com map não-None. Canal sem map → não entra em `maps` → valor nativo preservado.

- [ ] **Step 1: Escrever o teste de config que falha (map ausente é aceito)**

Adicionar em `hub/tests/test_config.py` (seguir o padrão `tmp_path`/YAML dos testes existentes; reusar o cabeçalho de config válido de `test_carrega_config_valida`):
```python
def test_canal_sem_map_fica_com_map_none(tmp_path):
    cfg_txt = """
    hub_id: HUB-0001
    coletor_id: COL-RS485-BUS0
    firmware_version: 0.1.0
    timezone_offset: "-03:00"
    intervalo_leitura_s: 60
    caminho_chave: /tmp/coletor.pem
    caminho_dados: /tmp/dados
    mqtt: {host: localhost, port: 1883}
    barramentos:
      - porta: /dev/ttyUSB1
        baud: 9600
        paridade: N
        stop_bits: 1
        dispositivos:
          - endereco: 2
            driver: rs_ws_n01_2d
            canais:
              - ch: 2
                sensor_id: TEMP-HENKE
                area_id: AREA-EXPURGO
                tipo_medida: temperatura
                unidade: C
                protocolo_origem: modbus
    """
    import textwrap
    p = tmp_path / "c.yaml"
    p.write_text(textwrap.dedent(cfg_txt))
    from hub import config
    cfg = config.carregar_config(p)
    canal = cfg.barramentos[0].dispositivos[0].canais[0]
    assert canal.map_in is None
    assert canal.map_out is None
    assert canal.ch == 2
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub/tests/test_config.py::test_canal_sem_map_fica_com_map_none -v`
Expected: FAIL com `KeyError: 'map'` em `_canal` (hoje o map é obrigatório).

- [ ] **Step 3: Tornar o map opcional em config.py**

Em `CanalConfig`, dar default `None` a `map_in`/`map_out`:
```python
@dataclass
class CanalConfig:
    ch: int
    sensor_id: str
    area_id: str
    tipo_medida: str
    unidade: str
    protocolo_origem: str
    map_in: tuple = None
    map_out: tuple = None
    filtro: dict = None
    calibracao: dict = None
```
Em `_canal`, parsear map só se presente:
```python
def _canal(bruto):
    for campo in ("sensor_id", "area_id"):
        validar_identificador(str(bruto[campo]))
    mapa = bruto.get("map")
    if mapa is not None:
        map_in = _par(mapa["in"], "map.in")
        map_out = _par(mapa["out"], "map.out")
    else:
        map_in = map_out = None
    cal = bruto.get("calibracao") or {}
    calibracao = {
        'cert_ver': int(cal.get('cert_ver', 0)),
        'ganho': float(cal.get('ganho', 1.0)),
        'offset': float(cal.get('offset', 0.0)),
    }
    return CanalConfig(
        ch=int(bruto["ch"]),
        sensor_id=bruto["sensor_id"],
        area_id=bruto["area_id"],
        tipo_medida=bruto["tipo_medida"],
        unidade=bruto["unidade"],
        protocolo_origem=bruto.get("protocolo_origem", "4-20ma"),
        map_in=map_in,
        map_out=map_out,
        filtro=bruto.get("filtro"),
        calibracao=calibracao,
    )
```

- [ ] **Step 4: Rodar e ver passar (config)**

Run: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub/tests/test_config.py -v`
Expected: PASS — o novo teste passa e `test_rejeita_map_com_tamanho_errado` (map presente porém errado) continua falhando corretamente via `_par`.

- [ ] **Step 5: Escrever o teste do leitor que falha (canal sem map preserva valor nativo)**

Adicionar em `hub/tests/test_leitor.py`. O driver-fake devolve um `value` nativo; com map ausente, `_specs` não deve gerar `MapSpec` para o canal, e o valor tem que chegar intacto. Reaproveitar `_DriverFake`/`_BackendFake` existentes. Construir um `CanalConfig` sem map e um leitor:
```python
def test_canal_sem_map_preserva_valor_nativo(tmp_path):
    from hub.config import CanalConfig
    from hub.leitor import Leitor
    canal = CanalConfig(
        ch=2, sensor_id='TEMP-HENKE', area_id='AREA-EXPURGO',
        tipo_medida='temperatura', unidade='C', protocolo_origem='modbus',
        map_in=None, map_out=None,
    )
    leitor = object.__new__(Leitor)
    from hub import modbus_backend
    leitor._backend = modbus_backend
    # _specs NÃO deve incluir o canal sem map:
    assert leitor._specs([canal]) == []
```

- [ ] **Step 6: Rodar e ver falhar (leitor)**

Run: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub/tests/test_leitor.py::test_canal_sem_map_preserva_valor_nativo -v`
Expected: FAIL — `_specs` hoje tenta `c.map_in[0]` com `None` → `TypeError`.

- [ ] **Step 7: Filtrar canais sem map em `_specs`**

Em `hub/leitor.py`:
```python
    def _specs(self, canais):
        return [
            self._backend.MapSpec(
                channels={c.ch}, in_min=c.map_in[0], in_max=c.map_in[1],
                out_min=c.map_out[0], out_max=c.map_out[1], unit=c.unidade,
            )
            for c in canais
            if c.map_in is not None and c.map_out is not None
        ]
```

- [ ] **Step 8: Rodar e ver passar + suíte hub**

Run: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub -q`
Expected: PASS — novo teste do leitor passa; testes de resiliência do Plano A e demais continuam verdes.

- [ ] **Step 9: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add hub/config.py hub/leitor.py hub/tests/test_config.py hub/tests/test_leitor.py
git commit -m "feat(hub): map opcional por canal (valor nativo quando ausente)

CanalConfig.map_in/out default None; _canal aceita map ausente; _specs so
gera MapSpec para canais com map real. Canal sem map recebe o valor nativo
do driver (ex.: RS-WS-N01-2D entrega C/%RH direto). Mata o map:[0,0] que
zerava a leitura.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Adapter por família + dispatch + leitor consome `ler`

**Files:**
- Modify: `hub/modbus_backend.py` (adapters + `criar_driver`)
- Modify: `hub/leitor.py` (`ler_todos` chama `ler`; `fechar` inalterado)
- Test: novo `hub/tests/test_modbus_backend.py`; `hub/tests/test_leitor.py` (renomear `read_channels`→`ler` nos fakes)

**Interfaces:**
- Consumes: submódulo com `rs_ws_n01_2d.py` (Task 1); map opcional (Task 2).
- Produces: `criar_driver` devolve `AdaptadorN4` ou `AdaptadorRS`, ambos com `ler(maps)` e `close()`. `leitor` chama `disp.driver.ler(maps=…)`.

- [ ] **Step 1: Escrever os testes do adapter que falham**

Criar `hub/tests/test_modbus_backend.py`:
```python
"""Adapters de driver: interface uniforme ler(maps)/close sobre o vendor."""
from hub.modbus_backend import AdaptadorN4, AdaptadorRS


class _VendorN4Fake:
    """Simula N4AIB16.read_channels: entries já têm 'channel'."""
    def __init__(self):
        self.fechado = False
        self.maps_recebido = "NAO_CHAMADO"
    def read_channels(self, maps=None):
        self.maps_recebido = maps
        return [{"channel": 1, "value": 12.5, "unit": "mA", "register": 0}]
    def close(self):
        self.fechado = True


class _VendorRSFake:
    """Simula RSWSN012D.read_measurements: entries têm 'name'/'register', SEM 'channel'."""
    def __init__(self):
        self.fechado = False
        self.maps_recebido = "NAO_CHAMADO"
    def read_measurements(self, maps=None):
        self.maps_recebido = maps
        return [
            {"name": "humidity", "register": 0, "value": 50.8, "unit": "%RH"},
            {"name": "temperature", "register": 1, "value": 25.9, "unit": "C"},
        ]
    def close(self):
        self.fechado = True


def test_adaptador_n4_repassa_entries_e_maps():
    vendor = _VendorN4Fake()
    ad = AdaptadorN4(vendor)
    entries = ad.ler(maps=["SPEC"])
    assert vendor.maps_recebido == ["SPEC"]           # maps repassado
    assert entries[0]["channel"] == 1                 # channel intacto
    assert entries[0]["value"] == 12.5


def test_adaptador_rs_injeta_channel_1based():
    vendor = _VendorRSFake()
    ad = AdaptadorRS(vendor)
    entries = ad.ler(maps=None)
    assert [e["channel"] for e in entries] == [1, 2]  # 1=umidade, 2=temp
    assert entries[0]["value"] == 50.8 and entries[0]["unit"] == "%RH"
    assert entries[1]["value"] == 25.9 and entries[1]["unit"] == "C"


def test_adaptadores_delegam_close():
    v1, v2 = _VendorN4Fake(), _VendorRSFake()
    AdaptadorN4(v1).close()
    AdaptadorRS(v2).close()
    assert v1.fechado and v2.fechado
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub/tests/test_modbus_backend.py -v`
Expected: FAIL com `ImportError: cannot import name 'AdaptadorN4'`.

- [ ] **Step 3: Implementar os adapters + dispatch**

Em `hub/modbus_backend.py`, adicionar após o import de `MapSpec`:
```python
class _AdaptadorDriver:
    """Interface uniforme que o leitor consome: ler(maps) + close().

    Confina no seam do vendor a diferença de nome de método e de forma das
    entries entre famílias de driver.
    """
    def __init__(self, driver):
        self._driver = driver

    def close(self):
        self._driver.close()


class AdaptadorN4(_AdaptadorDriver):
    """N4AIB16: read_channels já devolve entries com 'channel'."""
    def ler(self, maps=None):
        return self._driver.read_channels(maps=maps)


class AdaptadorRS(_AdaptadorDriver):
    """RS-WS-N01-2D: read_measurements devolve 'name'/'register'; injeta channel."""
    def ler(self, maps=None):
        entries = self._driver.read_measurements(maps=maps)
        for i, entry in enumerate(entries):
            entry["channel"] = i + 1
        return entries
```
Reescrever `criar_driver`:
```python
def criar_driver(driver_nome, porta, baud, paridade, stopbits, endereco):
    """Instancia o adapter do dispositivo. Raise ValueError se desconhecido."""
    if driver_nome == "n4aib16":
        from drivers.n4aib16 import N4AIB16
        return AdaptadorN4(N4AIB16(
            port=porta, baud=baud, address=endereco,
            parity=_PARIDADE.get(paridade, "N"), stopbits=stopbits,
        ))
    if driver_nome == "rs_ws_n01_2d":
        from drivers.rs_ws_n01_2d import RSWSN012D
        return AdaptadorRS(RSWSN012D(
            port=porta, baud=baud, address=endereco,
            parity=_PARIDADE.get(paridade, "N"), stopbits=stopbits,
        ))
    raise ValueError(f"driver Modbus desconhecido: {driver_nome!r}")
```

- [ ] **Step 4: Rodar os testes do adapter e ver passar**

Run: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub/tests/test_modbus_backend.py -v`
Expected: PASS (3 testes).

- [ ] **Step 5: Escrever o teste de dispatch do criar_driver (sem serial)**

Adicionar em `hub/tests/test_modbus_backend.py` — mockar os construtores do vendor (que abrem porta serial) via `monkeypatch`:
```python
def test_criar_driver_despacha_rs(monkeypatch):
    import hub.modbus_backend as mb

    class _RSFake:
        def __init__(self, **kw): self.kw = kw
    # patch no ponto de import lazy: injeta um módulo drivers.rs_ws_n01_2d falso
    import sys, types
    mod = types.ModuleType("drivers.rs_ws_n01_2d")
    mod.RSWSN012D = _RSFake
    monkeypatch.setitem(sys.modules, "drivers.rs_ws_n01_2d", mod)
    ad = mb.criar_driver("rs_ws_n01_2d", "/dev/ttyUSB1", 9600, "N", 1, 2)
    assert isinstance(ad, mb.AdaptadorRS)
    assert ad._driver.kw["address"] == 2 and ad._driver.kw["baud"] == 9600


def test_criar_driver_despacha_n4(monkeypatch):
    import hub.modbus_backend as mb, sys, types
    class _N4Fake:
        def __init__(self, **kw): self.kw = kw
    mod = types.ModuleType("drivers.n4aib16")
    mod.N4AIB16 = _N4Fake
    monkeypatch.setitem(sys.modules, "drivers.n4aib16", mod)
    ad = mb.criar_driver("n4aib16", "/dev/ttyUSB0", 9600, "N", 1, 1)
    assert isinstance(ad, mb.AdaptadorN4)


def test_criar_driver_desconhecido_levanta():
    import hub.modbus_backend as mb
    import pytest
    with pytest.raises(ValueError):
        mb.criar_driver("driver_inexistente", "/dev/x", 9600, "N", 1, 1)
```

- [ ] **Step 6: Rodar e ver passar**

Run: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub/tests/test_modbus_backend.py -v`
Expected: PASS (6 testes).

- [ ] **Step 7: Trocar `read_channels`→`ler` no leitor e nos fakes**

Em `hub/leitor.py`, em `ler_todos`, trocar a chamada:
```python
                lidos = disp.driver.ler(maps=self._specs(disp.canais))
```
(`fechar` continua chamando `disp.driver.close()` — o adapter tem `close()`.)

Em `hub/tests/test_leitor.py`, os fakes que o `leitor` chama expõem hoje `read_channels`; renomear para `ler` (o `leitor` agora chama `ler` no que o backend devolve). São: `_DriverFake.read_channels` → `ler`; `_DriverExplode.read_channels` → `ler`; qualquer outro driver-fake com `read_channels`. Manter o método `close` onde existir. NÃO alterar a lógica dos testes, só o nome do método.

Exemplo (`_DriverFake`):
```python
class _DriverFake:
    def __init__(self, valores=None, erro=False):
        self._valores = valores or [{"channel": 1, "value": 50.0, "unit": "C"}]
        self._erro = erro
    def ler(self, maps=None):
        if self._erro:
            raise RuntimeError("sem resposta")
        return self._valores
    def close(self):
        pass
```

- [ ] **Step 8: Rodar a suíte hub inteira (regressão)**

Run: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub -q`
Expected: PASS — todos os testes de leitor (resiliência do Plano A inclusa), config, backend e vendor verdes. Se algum fake ainda expõe `read_channels`, o teste correspondente falha com `AttributeError: 'X' object has no attribute 'ler'` → renomear o que faltou.

- [ ] **Step 9: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add hub/modbus_backend.py hub/leitor.py hub/tests/test_modbus_backend.py hub/tests/test_leitor.py
git commit -m "feat(hub): adapter por familia + leitor consome interface unica ler()

criar_driver devolve AdaptadorN4/AdaptadorRS (ler(maps)/close); RS injeta
channel=i+1 nas entries de read_measurements. leitor chama ler() em vez de
read_channels. Cabeia o RS-WS-N01-2D sem o leitor saber de vendor.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- §Arquitetura Componente 1 (criar_driver devolve adapter) → Task 3. ✓
- §Componente 2 (interface uniforme ler/close; RS injeta channel; N4 repassa) → Task 3 Steps 3 + testes 1. ✓
- §Componente 3 (map opcional: CanalConfig/_canal/_specs) → Task 2. ✓
- §Componente 4 (bump submódulo fc70ffb, pin SHA, N4 inalterado) → Task 1. ✓
- §Estratégia de testes 1-6 → adapter normaliza (T3 S1), N4 repassa (T3 S1), criar_driver despacha (T3 S5), map opcional leitor (T2 S5), config aceita map ausente (T2 S1), regressão leitor (T2 S8 / T3 S8). ✓

**Placeholder scan:** sem TBD/TODO; todo código mostrado. ✓

**Type consistency:** adapter expõe `ler(maps)`/`close()` em T3 e é o que `leitor` chama em T3 S7 — consistente. `CanalConfig.map_in/out` default None em T2 S3, consumido por `_specs` em T2 S7 e pelo teste T2 S5 — consistente. `criar_driver` devolve `AdaptadorN4`/`AdaptadorRS` (T3 S3), testado em T3 S5 — consistente.

**Ordem/dependência:** T1 (submódulo) e T2 (map opcional) são independentes entre si; T3 depende de ambas (import do RS + map nativo). Executar T1 → T2 → T3.

**Nota:** o teste T2 S5 usa `object.__new__(Leitor)` + `_backend` para exercitar `_specs` isolado sem abrir serial (padrão já usado em `test_normalizar_aplica_calibracao_e_carimba_coeficientes`).
