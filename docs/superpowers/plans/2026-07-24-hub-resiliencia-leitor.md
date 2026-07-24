# Resiliência do loop de leitura do Hub — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Falha de um dispositivo (na construção ou na leitura) degrada só aquele dispositivo — seus canais viram `sensor_offline` e o hub segue vivo — em vez de matar o processo inteiro.

**Architecture:** Dois pontos de isolamento em `hub/leitor.py`: (1) o loop de leitura `ler_todos` captura qualquer exceção por dispositivo (hoje só `RuntimeError`); (2) o construtor `Leitor.__init__` captura falha de `criar_driver` por dispositivo, guardando seus canais numa lista `_degradados` que `ler_todos` emite como `sensor_offline` a cada ciclo. Log dedupe por transição de estado (ok↔falha) evita spam.

**Tech Stack:** Python 3, pytest. Sem novas dependências. Hub loga com `print(f"[hub] ...")` (não `logging` stdlib).

## Global Constraints

- Reusar o status de leitura existente `sensor_offline` — NÃO introduzir novo valor de status.
- Log segue o padrão do hub: `print(f"[hub] ...")` (ver `hub/main.py:38`, `hub/enviador_sftp.py:72`).
- Escopo é SÓ `hub/leitor.py` + `hub/tests/test_leitor.py`. Nada de addon Odoo, serializer, ou submódulo.
- Testes usam o padrão existente em `hub/tests/test_leitor.py`: `_BackendFake(driver)` com `criar_driver` que devolve um driver injetado; `_DriverFake` com `read_channels`.
- Rodar testes: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub/tests/test_leitor.py -q`.

---

## Estado atual de `hub/leitor.py` (referência)

```python
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
```

Construtor atual:

```python
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
```

---

## Task 1: Isolar falha na leitura (`ler_todos` captura qualquer exceção)

**Files:**
- Modify: `hub/leitor.py` (`ler_todos`, ~linha 46-61)
- Test: `hub/tests/test_leitor.py`

**Interfaces:**
- Consumes: nada novo.
- Produces: `ler_todos(agora)` continua devolvendo `list[dict]`; dispositivo que estoura em `read_channels` com QUALQUER exceção (não só `RuntimeError`) marca todos os seus canais `sensor_offline` e a varredura segue.

- [ ] **Step 1: Escrever o teste que falha (IndexError isola)**

Adicionar em `hub/tests/test_leitor.py`. Precisa de um config com 2 dispositivos em 2 endereços do mesmo barramento; o backend fake deve devolver drivers distintos por endereço. Como o `_BackendFake` atual devolve sempre o mesmo driver, criar um fake multi-driver:

```python
class _BackendMulti:
    """Backend fake que despacha driver por endereço do dispositivo."""
    def __init__(self, por_endereco):
        self._por_endereco = por_endereco  # dict[int, driver]
        from hub.modbus_backend import MapSpec
        self.MapSpec = MapSpec
    def criar_driver(self, driver_nome, porta, baud, paridade, stopbits, endereco):
        return self._por_endereco[endereco]


class _DriverExplode:
    """Driver que estoura com uma exceção arbitrária (não RuntimeError)."""
    def __init__(self, exc):
        self._exc = exc
    def read_channels(self, maps=None):
        raise self._exc
    def close(self):
        pass


CFG_2DISP = """
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
                sensor_id: SNR-BOM
                area_id: AREA-EXPURGO
                tipo_medida: temperatura
                unidade: C
                protocolo_origem: 4-20ma
                map: {in: [4, 20], out: [0, 100]}
          - endereco: 2
            driver: n4aib16
            canais:
              - ch: 1
                sensor_id: SNR-RUIM
                area_id: AREA-EXPURGO
                tipo_medida: temperatura
                unidade: C
                protocolo_origem: 4-20ma
                map: {in: [4, 20], out: [0, 100]}
"""


def _cfg2(tmp_path):
    p = tmp_path / "c2.yaml"
    p.write_text(textwrap.dedent(CFG_2DISP))
    return config.carregar_config(p)


def test_indexerror_num_dispositivo_nao_derruba_os_outros(tmp_path):
    bom = _DriverFake([{"channel": 1, "value": 42.0, "unit": "C"}])
    ruim = _DriverExplode(IndexError("list index out of range"))
    backend = _BackendMulti({1: bom, 2: ruim})
    leitor = Leitor(_cfg2(tmp_path), backend=backend)
    leituras = leitor.ler_todos(datetime(2026, 7, 24, 0, 1, tzinfo=TZ))
    por_sensor = {r["sensor_id"]: r for r in leituras}
    assert por_sensor["SNR-BOM"]["status_leitura"] == "ok"
    assert por_sensor["SNR-BOM"]["valor"] == 42.0
    assert por_sensor["SNR-RUIM"]["status_leitura"] == "sensor_offline"
    assert por_sensor["SNR-RUIM"]["valor"] == 0.0
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub/tests/test_leitor.py::test_indexerror_num_dispositivo_nao_derruba_os_outros -v`
Expected: FAIL — o `IndexError` escapa do `except RuntimeError` e a chamada `ler_todos` levanta (não devolve a lista).

- [ ] **Step 3: Ampliar o except para qualquer exceção + log por transição**

Em `hub/leitor.py`, no `__init__` adicionar rastreio de dispositivos já em falha (pra dedupe de log). Adicionar `self._falhados = set()` ao fim do `__init__`. Trocar o `except RuntimeError:` de `ler_todos` por:

```python
            except Exception as e:
                chave = id(disp)
                if chave not in self._falhados:
                    self._falhados.add(chave)
                    print(f"[hub] leitura falhou, dispositivo offline: "
                          f"driver={disp.canais[0].sensor_id if disp.canais else '?'} erro={e!r}")
                for canal in disp.canais:
                    leituras.append(self._normalizar(canal, 0.0, "sensor_offline", agora))
            else:
                self._falhados.discard(id(disp))
```

Nota: o `else` do try roda quando NÃO houve exceção — usado pra limpar o marcador de falha (transição falha→ok volta a logar na próxima falha). O `por_canal`/append de sucesso já está dentro do `try`; o `else` só faz o discard.

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub/tests/test_leitor.py::test_indexerror_num_dispositivo_nao_derruba_os_outros -v`
Expected: PASS

- [ ] **Step 5: Rodar a suíte inteira do leitor (regressão)**

Run: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub/tests/test_leitor.py -q`
Expected: PASS — incluindo `test_dispositivo_offline_vira_sensor_offline` (RuntimeError continua virando `sensor_offline`; agora via o `except Exception` mais amplo) e `test_ler_todos_normaliza`.

- [ ] **Step 6: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add hub/leitor.py hub/tests/test_leitor.py
git commit -m "fix(leitor): isola falha de leitura por dispositivo (except Exception)

Qualquer excecao em read_channels (nao so RuntimeError) marca os canais
do dispositivo como sensor_offline e a varredura segue. Log dedupe por
transicao ok<->falha. Fecha o SPOF do IndexError que matava o hub inteiro.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Isolar falha na construção (`__init__` degrada dispositivo que não instancia)

**Files:**
- Modify: `hub/leitor.py` (`__init__`, ~linha 16-25; `ler_todos` para emitir os degradados)
- Test: `hub/tests/test_leitor.py`

**Interfaces:**
- Consumes: `self._falhados` (set) e `self._dispositivos` da Task 1.
- Produces: `Leitor.__init__` NÃO levanta quando `criar_driver` estoura para um dispositivo; os canais desse dispositivo entram em `self._degradados` (lista de `list[CanalConfig]`, uma por dispositivo). `ler_todos` emite `sensor_offline` para cada canal degradado a cada ciclo.

- [ ] **Step 1: Escrever o teste que falha (driver desconhecido não mata o boot)**

Adicionar em `hub/tests/test_leitor.py`. Backend cujo `criar_driver` estoura para o endereço 2:

```python
class _BackendConstrucaoFalha:
    """criar_driver devolve driver bom no endereço 1 e estoura no 2."""
    def __init__(self, driver_bom):
        self._bom = driver_bom
        from hub.modbus_backend import MapSpec
        self.MapSpec = MapSpec
    def criar_driver(self, driver_nome, porta, baud, paridade, stopbits, endereco):
        if endereco == 2:
            raise ValueError(f"driver Modbus desconhecido: {driver_nome!r}")
        return self._bom


def test_dispositivo_que_nao_instancia_nao_derruba_boot(tmp_path):
    bom = _DriverFake([{"channel": 1, "value": 42.0, "unit": "C"}])
    backend = _BackendConstrucaoFalha(bom)
    # NÃO deve levantar:
    leitor = Leitor(_cfg2(tmp_path), backend=backend)
    leituras = leitor.ler_todos(datetime(2026, 7, 24, 0, 1, tzinfo=TZ))
    por_sensor = {r["sensor_id"]: r for r in leituras}
    # dispositivo bom publica normal
    assert por_sensor["SNR-BOM"]["status_leitura"] == "ok"
    assert por_sensor["SNR-BOM"]["valor"] == 42.0
    # dispositivo que não instanciou vira sensor_offline (visível no dashboard)
    assert por_sensor["SNR-RUIM"]["status_leitura"] == "sensor_offline"
    assert por_sensor["SNR-RUIM"]["valor"] == 0.0
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub/tests/test_leitor.py::test_dispositivo_que_nao_instancia_nao_derruba_boot -v`
Expected: FAIL — `criar_driver` levanta `ValueError` no `__init__`, então `Leitor(...)` propaga a exceção antes de qualquer leitura.

- [ ] **Step 3: Envolver a criação por-dispositivo em try/except + emitir degradados**

Em `hub/leitor.py`, reescrever o `__init__`:

```python
    def __init__(self, config, backend=_backend_padrao):
        self._config = config
        self._backend = backend
        self._dispositivos = []
        self._degradados = []   # list[list[CanalConfig]] — dispositivos que não instanciaram
        self._falhados = set()
        for bus in config.barramentos:
            for disp in bus.dispositivos:
                try:
                    driver = backend.criar_driver(
                        disp.driver, bus.porta, bus.baud, bus.paridade, bus.stop_bits, disp.endereco,
                    )
                except Exception as e:
                    print(f"[hub] dispositivo nao instanciou, degradado: "
                          f"driver={disp.driver!r} porta={bus.porta} endereco={disp.endereco} erro={e!r}")
                    self._degradados.append(disp.canais)
                    continue
                self._dispositivos.append(_DispositivoLigado(driver, disp.canais))
```

E em `ler_todos`, ao fim (antes do `return leituras`), emitir os degradados:

```python
        for canais in self._degradados:
            for canal in canais:
                leituras.append(self._normalizar(canal, 0.0, "sensor_offline", agora))
        return leituras
```

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub/tests/test_leitor.py::test_dispositivo_que_nao_instancia_nao_derruba_boot -v`
Expected: PASS

- [ ] **Step 5: Rodar a suíte inteira do leitor (regressão)**

Run: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub/tests/test_leitor.py -q`
Expected: PASS — todos os testes anteriores + os dois novos.

- [ ] **Step 6: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add hub/leitor.py hub/tests/test_leitor.py
git commit -m "fix(leitor): dispositivo que nao instancia degrada em vez de matar boot

criar_driver estourando (driver desconhecido, porta inexistente) nao aborta
mais o Leitor inteiro; os canais do dispositivo entram em _degradados e sao
emitidos como sensor_offline a cada ciclo, ficando visiveis no dashboard.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- §Fix 1 (ler_todos except Exception) → Task 1. ✓
- §Fix 2 (construtor try/except + _degradados emitindo offline) → Task 2. ✓
- §Log (print padrão hub, dedupe transição na leitura, uma vez no boot na construção) → Task 1 Step 3 (dedupe leitura) + Task 2 Step 3 (log construção). ✓
- §Testes 1-4 → Task 1 cobre "leitura estoura não-RuntimeError" (teste 1) e regressão RuntimeError (teste 4, via suíte); Task 2 cobre "construção falha" (teste 2) e "construção falha + dispositivo bom" (teste 3, no mesmo teste `_nao_derruba_boot`). ✓
- §Decisão do usuário (emitir offline, não omitir) → Task 2 Step 3 emite. ✓

**Placeholder scan:** nenhum TBD/TODO; todo código mostrado. ✓

**Type consistency:** `self._falhados` (set, id(disp)) criado na Task 1 Step 3 e no `__init__` da Task 2 Step 3 — consistente (Task 2 reescreve o `__init__` completo incluindo `self._falhados = set()`). `self._degradados` (list de list[CanalConfig]) criado na Task 2. `_normalizar(canal, valor, status, agora)` — assinatura existente, usada igual. ✓

**Nota de ordem:** Task 2 reescreve o `__init__` inteiro (que a Task 1 tocou só adicionando `self._falhados = set()` ao fim). Ao aplicar Task 2, garantir que `self._falhados = set()` permaneça no `__init__` reescrito (já incluído no bloco do Step 3 da Task 2). Sem conflito.
