# Driver genérico register-driven (Plano C2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um driver Modbus data-driven (`generico`) que lê registradores por um spec vindo do Odoo, sem código por dispositivo — provado por equivalência unitária do decode contra o driver RS específico.

**Architecture:** Driver `generico` no submódulo `modbus-connector` (int16/uint16 v1, `probe` por registrador, escala/offset, reuso de filters/scaling). Encanamento aditivo: `criar_driver(..., registros=None)`; o `leitor` deriva `registros` dos canais com `registro`; `AdaptadorGenerico` no seam. Serializer emite `registro` só para dispositivos com `driver=generico`. Henke de produção fica no driver específico — sem cutover.

**Tech Stack:** Python (submódulo usa `unittest`+`mock`; hub/api usam `pytest`), Odoo 16 addon, YAML.

## Global Constraints

- v1: `data_type` ∈ {`int16` signed, `uint16` unsigned}, 1 registrador (`count==1`). `int32/uint32/float32`/`count>1` → `NotImplementedError` (submódulo) e `ConfigInvalida` (serializer). Decode isolado numa função pura, estruturado para extensão.
- `probe` por registrador (`function_code` varia por registrador). `function` int: `'03_holding'`→3, `'04_input'`→4.
- Decode: `int16` → `raw-0x10000 se raw>=0x8000` (signed); `uint16` → raw. Depois `valor = raw_decodificado * scale + offset`.
- Interface do driver: `read_measurements(maps=None)` → entries `{channel, value, unit, ...}`; `close()`. Reusa o adapter (`AdaptadorGenerico.ler(maps)`).
- Encanamento aditivo: N4/RS ignoram `registros` (None), config inalterada.
- Serializer emite `registro` SÓ para `driver=generico`. Henke de produção continua `rs_ws_n01_2d` — sem cutover.
- Vetores de equivalência (gate): temp int16 scale 0.1 → raw 245 = 24.5, raw 65516 (0xFFEC) = -2.0; umid uint16 scale 0.1 → raw 545 = 54.5.
- Submódulo é repo separado (`hub/vendor/modbus-connector`, remoto `github.com/afonsorcarvalho/modbus-connector`, hoje pinado em `fc70ffb`): commit + push origin/main + bump do ponteiro no parent.

## Estado atual (referência)

Submódulo `drivers/rs_ws_n01_2d.py` (padrão a espelhar): importa `probe`/`open_serial` de `modbus_scanner` (top-level via sys.path), `reduce/EWMA` de `common.filters`, `resolve_maps` de `common.scaling`. `read_measurements(samples=1, ..., maps=None)` itera registradores, aplica pipeline + map opcional, retorna entries. Teste (`tests/test_rs_ws_n01_2d.py`): `unittest`, `patch("drivers.rs_ws_n01_2d.open_serial", ...)`, sobrescreve `dev.read_raw = lambda: [495, 243]`.

`hub/modbus_backend.py:criar_driver(driver_nome, porta, baud, paridade, stopbits, endereco)` → `AdaptadorN4`/`AdaptadorRS`. `hub/leitor.py:__init__` chama `criar_driver(disp.driver, bus.porta, bus.baud, bus.paridade, bus.stop_bits, disp.endereco)`. `hub/config.py:CanalConfig` tem `map_in/map_out` opcionais (C1/B).

---

## Task 1: Driver genérico no submódulo + decode + testes + push + bump

**Files:**
- Create (submódulo): `hub/vendor/modbus-connector/drivers/generico.py`
- Create (submódulo): `hub/vendor/modbus-connector/tests/test_generico.py`
- Modify: `hub/vendor/modbus-connector` (ponteiro do submódulo, após push)
- Test (parent): `hub/tests/test_vendor_drivers.py` (smoke import)

**Interfaces:**
- Produces: `drivers.generico.Generico(port, baud, address, parity, stopbits, registros)` com `read_measurements(maps=None)` → entries `{channel,value,unit,...}` e `close()`; função pura `decode_registro(words, data_type)`.

- [ ] **Step 1: Escrever os testes que falham (submódulo, unittest)**

Criar `hub/vendor/modbus-connector/tests/test_generico.py`. Espelhar o padrão de `tests/test_rs_ws_n01_2d.py` (patch de `open_serial`). Testar:
```python
import unittest
from unittest.mock import patch
from drivers.generico import Generico, decode_registro


class TestDecode(unittest.TestCase):
    def test_int16_signed(self):
        self.assertEqual(decode_registro([245], 'int16'), 245)
        self.assertEqual(decode_registro([65516], 'int16'), -20)   # 0xFFEC -> -20 (antes da escala)
    def test_uint16(self):
        self.assertEqual(decode_registro([545], 'uint16'), 545)
    def test_count_maior_que_1_nao_suportado(self):
        with self.assertRaises(NotImplementedError):
            decode_registro([1, 2], 'int32')
    def test_data_type_desconhecido(self):
        with self.assertRaises(NotImplementedError):
            decode_registro([1], 'float32')


def _dev(registros):
    with patch("drivers.generico.open_serial", return_value=object()):
        return Generico(port="/dev/null", baud=9600, address=2,
                        parity="N", stopbits=1, registros=registros)


class TestReadMeasurements(unittest.TestCase):
    def test_le_e_decodifica_por_registrador(self):
        registros = [
            {'ch': 1, 'address': 0, 'function': 3, 'data_type': 'uint16', 'scale': 0.1, 'offset': 0.0, 'count': 1},
            {'ch': 2, 'address': 1, 'function': 3, 'data_type': 'int16', 'scale': 0.1, 'offset': 0.0, 'count': 1},
        ]
        dev = _dev(registros)
        # probe(ser, address, function, start, count) -> (ok, msg, words)
        respostas = {0: (True, 'ok', [545]), 1: (True, 'ok', [245])}
        with patch("drivers.generico.probe", side_effect=lambda ser, addr, fn, start, cnt, **k: respostas[start]):
            entries = dev.read_measurements()
        por_ch = {e['channel']: e for e in entries}
        self.assertAlmostEqual(por_ch[1]['value'], 54.5)   # umid uint16
        self.assertAlmostEqual(por_ch[2]['value'], 24.5)   # temp int16

    def test_temp_negativa(self):
        registros = [{'ch': 2, 'address': 1, 'function': 3, 'data_type': 'int16', 'scale': 0.1, 'offset': 0.0, 'count': 1}]
        dev = _dev(registros)
        with patch("drivers.generico.probe", side_effect=lambda *a, **k: (True, 'ok', [65516])):
            entries = dev.read_measurements()
        self.assertAlmostEqual(entries[0]['value'], -2.0)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /home/afonso/docker/odoo_sentinela/hub/vendor/modbus-connector && python -m pytest tests/test_generico.py -q`
Expected: FAIL — `drivers.generico` não existe.

- [ ] **Step 3: Implementar `drivers/generico.py`**

Espelhar o cabeçalho de imports de `rs_ws_n01_2d.py` (sys.path para `modbus_scanner`, `probe`/`open_serial`; `reduce/reject_outliers/EWMA` de `common.filters`; `resolve_maps` de `common.scaling`). Implementar:
```python
def to_signed16(raw):
    return raw - 0x10000 if raw >= 0x8000 else raw


def decode_registro(words, data_type):
    """Decodifica words crus (int 16-bit) no valor bruto conforme data_type.

    v1: int16 (signed) e uint16 (unsigned), 1 registrador. Estruturado para
    int32/uint32/float32 + byte_order serem acréscimo delimitado depois.
    """
    if len(words) != 1:
        raise NotImplementedError(f"count={len(words)} não suportado na v1 (só 1 registrador)")
    word = words[0]
    if data_type == 'int16':
        return to_signed16(word)
    if data_type == 'uint16':
        return word
    raise NotImplementedError(f"data_type {data_type!r} não suportado na v1 (só int16/uint16)")


class Generico:
    """Driver Modbus data-driven: lê registradores por spec (address/function/
    data_type/scale/offset). Um probe por registrador."""

    def __init__(self, port, baud, address, parity="N", stopbits=1,
                 registros=None, timeout=0.3, ewma_alpha=None):
        self.address = address
        self.registros = registros or []
        self.ewma_alpha = ewma_alpha
        self._ewma = {}
        self._ser = open_serial(port, baud, 8, parity, stopbits, timeout)

    def _read_registro(self, reg, samples, interval):
        """Coleta `samples` leituras de um registrador; devolve o bruto reduzido."""
        brutos = []
        failures = 0
        while len(brutos) < samples:
            ok, msg, words = probe(self._ser, self.address, reg['function'],
                                   reg['address'], reg['count'])
            if not ok or words is None:
                failures += 1
                if failures > samples:
                    raise RuntimeError(f"Falha ao ler registro {reg['address']} @ addr {self.address}: {msg}")
                continue
            brutos.append(decode_registro(words, reg['data_type']))
            if interval and len(brutos) < samples:
                time.sleep(interval)
        return brutos

    def read_measurements(self, samples=1, method="mean", trim=0.1,
                          reject=False, reject_k=3.0, interval=0.0,
                          with_stats=False, maps=None):
        channel_maps = resolve_maps(maps) if maps else {}
        result = []
        for reg in self.registros:
            col = self._read_registro(reg, samples, interval)
            if reject:
                col = reject_outliers(col, reject_k)
            raw_reduced = reduce(col, method, trim) if len(col) > 1 else col[0]
            phys = raw_reduced * reg['scale'] + reg['offset']
            if self.ewma_alpha is not None:
                ewma = self._ewma.get(reg['ch'])
                if ewma is None:
                    ewma = EWMA(self.ewma_alpha)
                    self._ewma[reg['ch']] = ewma
                phys = ewma.update(phys)
            entry = {'channel': reg['ch'], 'value': round(phys, 3), 'unit': reg.get('unit', '')}
            spec = channel_maps.get(reg['ch'])
            if spec is not None:
                entry['value'] = round(spec.apply(phys), 4)
                entry['unit'] = spec.unit or 'eng'
            result.append(entry)
        return result

    def close(self):
        try:
            self._ser.close()
        except Exception:
            pass
```
(Importar `time` no topo. `probe`/`open_serial` importados de `modbus_scanner` como em `rs_ws_n01_2d.py`.)

- [ ] **Step 4: Rodar os testes do submódulo e ver passar**

Run: `cd /home/afonso/docker/odoo_sentinela/hub/vendor/modbus-connector && python -m pytest tests/test_generico.py -q`
Expected: PASS (todos). Rodar também a suíte inteira do submódulo para regressão: `python -m pytest tests/ -q`.

- [ ] **Step 5: Commit no submódulo e push para origin/main**

O submódulo está em HEAD destacado (`fc70ffb`). Levar para `main`, commitar e empurrar:
```bash
cd /home/afonso/docker/odoo_sentinela/hub/vendor/modbus-connector
git fetch origin main
git checkout main && git merge --ff-only fc70ffb 2>/dev/null || git checkout main
git add drivers/generico.py tests/test_generico.py
git commit -m "feat(generico): driver Modbus data-driven (int16/uint16 v1)

Le registradores por spec (address/function/data_type/scale/offset), um
probe por registrador. Decode isolado (decode_registro) estruturado p/
int32/float32 depois. Reusa filters/scaling.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin main
git rev-parse --short HEAD   # <- novo SHA do submodulo
```
Se o `main` local divergir de `fc70ffb`, PARAR e reportar (não forçar).

- [ ] **Step 6: Bump do ponteiro no parent + smoke test**

```bash
cd /home/afonso/docker/odoo_sentinela
git add hub/vendor/modbus-connector
```
Adicionar em `hub/tests/test_vendor_drivers.py`:
```python
def test_generico_importavel():
    from drivers.generico import Generico, decode_registro
    assert decode_registro([65516], 'int16') == -20
    assert hasattr(Generico, 'read_measurements')
```
Run: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub/tests/test_vendor_drivers.py -q`
Expected: PASS.

- [ ] **Step 7: Commit do bump no parent**

```bash
cd /home/afonso/docker/odoo_sentinela
git add hub/vendor/modbus-connector hub/tests/test_vendor_drivers.py
git commit -m "chore(hub): bump modbus-connector (driver generico)

Sobe o submodulo para o commit que adiciona drivers/generico.py; smoke test
confirma import + decode int16 signed.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Encanamento no hub (config + criar_driver + adapter + leitor)

**Files:**
- Modify: `hub/config.py` (`CanalConfig.registro` + validação genérico)
- Modify: `hub/modbus_backend.py` (`AdaptadorGenerico` + `criar_driver(registros=)`)
- Modify: `hub/leitor.py` (deriva e passa `registros`)
- Test: `hub/tests/test_config.py`, `hub/tests/test_modbus_backend.py`, `hub/tests/test_leitor.py`

**Interfaces:**
- Consumes: `drivers.generico.Generico` (Task 1).
- Produces: `CanalConfig.registro` (dict opcional); `criar_driver(..., registros=None)` → `AdaptadorGenerico`; `leitor` deriva `registros` dos canais.

- [ ] **Step 1: Config — teste que falha (registro parseado)**

Adicionar em `hub/tests/test_config.py`: YAML de dispositivo com `driver: generico` e canal com `registro: {address:1, function:3, data_type:int16, scale:0.1, offset:0.0, count:1}` → `CanalConfig.registro` populado. E validação: `driver generico` sem `registro` no canal → erro.

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub/tests/test_config.py -q`
Expected: FAIL — `CanalConfig` não tem `registro` / sem validação.

- [ ] **Step 3: Config — implementar**

Em `hub/config.py`: `CanalConfig` ganha `registro: dict = None`. Em `_canal`, ler `bruto.get('registro')` (parsear os campos como dict, sem transformação além de tipos). Em `_dispositivo`/`carregar_config`, se `disp.driver == 'generico'`: cada canal DEVE ter `registro` com `data_type ∈ {int16,uint16}` e `count == 1`; senão `ValueError` claro (fail-fast no boot).

- [ ] **Step 4: modbus_backend + leitor — teste que falha**

Adicionar em `hub/tests/test_modbus_backend.py`: `criar_driver('generico', porta, baud, 'N', 1, endereco, registros=[{...}])` → `AdaptadorGenerico` (mockar o construtor `Generico` para não abrir serial, padrão dos testes de dispatch existentes). `AdaptadorGenerico.ler(maps)` delega a `read_measurements` e repassa entries.
Adicionar em `hub/tests/test_leitor.py`: um `_BackendFake` cujo `criar_driver` recebe `registros` e devolve um driver-fake; leitor com config genérica passa `registros` derivado dos canais.

- [ ] **Step 5: Rodar e ver falhar**

Run: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub/tests/test_modbus_backend.py hub/tests/test_leitor.py -q`
Expected: FAIL — `AdaptadorGenerico`/param `registros` não existem.

- [ ] **Step 6: modbus_backend + leitor — implementar**

Em `hub/modbus_backend.py`:
```python
class AdaptadorGenerico(_AdaptadorDriver):
    """Driver genérico: read_measurements já devolve entries com 'channel'."""
    def ler(self, maps=None):
        return self._driver.read_measurements(maps=maps)
```
`criar_driver` ganha `registros=None` e o ramo:
```python
    if driver_nome == "generico":
        from drivers.generico import Generico
        return AdaptadorGenerico(Generico(
            port=porta, baud=baud, address=endereco,
            parity=_PARIDADE.get(paridade, "N"), stopbits=stopbits, registros=registros))
```
Em `hub/leitor.py:__init__`, derivar e passar:
```python
                registros = [{'ch': c.ch, **c.registro} for c in disp.canais if c.registro] or None
                driver = backend.criar_driver(
                    disp.driver, bus.porta, bus.baud, bus.paridade, bus.stop_bits, disp.endereco,
                    registros=registros,
                )
```
(Os `_BackendFake` dos testes existentes precisam aceitar `registros=None` em `criar_driver` — adicionar `**kwargs` ou o param.)

- [ ] **Step 7: Rodar a suíte hub e ver passar**

Run: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub -q`
Expected: PASS — novos testes + regressão (N4/RS/resiliência intactos; `criar_driver` com `registros=None` para N4/RS).

- [ ] **Step 8: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add hub/config.py hub/modbus_backend.py hub/leitor.py hub/tests/
git commit -m "feat(hub): encanamento do driver generico (registro no canal)

CanalConfig.registro + validacao boot; criar_driver(registros=) -> AdaptadorGenerico;
leitor deriva registros dos canais. N4/RS inalterados (registros=None).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Serializer emite register spec + Selection `generico`

**Files:**
- Modify: `addons/afr_sentinela_sensor_monitor/models/modbus_profile.py` (Selection `+generico`)
- Modify: `api/config_publisher.py` (emite `registro` para driver genérico)
- Test: `api/tests/test_config_serializer.py`

**Interfaces:**
- Consumes: config schema `registro` (Task 2).
- Produces: config gerada com `registro` no canal para dispositivos `driver=generico`; validação v1 (`data_type`/`count`).

- [ ] **Step 1: Selection — adicionar `generico`**

Em `addons/afr_sentinela_sensor_monitor/models/modbus_profile.py`, Selection do driver:
```python
    driver = fields.Selection(
        [('n4aib16', 'N4AIB16'), ('rs_ws_n01_2d', 'RS-WS-N01-2D'), ('generico', 'Genérico (register-driven)')],
        default='n4aib16', required=True, ...)
```
Aplicar no Odoo vivo: `docker exec odoo_sentinela-odoo-1 odoo -d sentinela -u afr_sentinela_sensor_monitor --test-enable --test-tags /afr_sentinela_sensor_monitor --http-port=8169 --stop-after-init` (upgrade), depois `docker restart odoo_sentinela-odoo-1` (registry vivo).

- [ ] **Step 2: Serializer — teste que falha (integração Odoo)**

Adicionar em `api/tests/test_config_serializer.py`: um helper que cria um perfil `driver='generico'` com um register (`function_code='03_holding', register_address=1, data_type='int16', scale=0.1, register_count=1`) e um sensor linkado; `serializar_config_hub` → o canal tem `registro: {address:1, function:3, data_type:'int16', scale:0.1, offset:.., count:1}`. E: register com `data_type='float32'` ou `register_count=2` → `ConfigInvalida`. E regressão: perfil N4/RS NÃO emite `registro`.

- [ ] **Step 3: Rodar e ver falhar**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. .venv/bin/python -m pytest api/tests/test_config_serializer.py -q`
Expected: FAIL — serializer não emite `registro`.

- [ ] **Step 4: Serializer — implementar**

Em `api/config_publisher.py`: quando `driver == 'generico'`, para cada sensor, ler o `modbus.profile.register` linkado (via `modbus_register_id`) com `fields=['function_code','register_address','register_count','data_type','scale','offset','unidade']` e emitir no canal:
```python
_FUNCAO = {'03_holding': 3, '04_input': 4}
_DATATYPES_V1 = {'int16', 'uint16'}
...
if driver == 'generico':
    reg = ...  # o register do sensor
    if reg['data_type'] not in _DATATYPES_V1 or reg['register_count'] != 1:
        raise ConfigInvalida(f"sensor {s['sensor_code']}: driver generico v1 só suporta "
                             f"int16/uint16 e 1 registrador (veio {reg['data_type']}, count {reg['register_count']})")
    canal['registro'] = {
        'address': reg['register_address'],
        'function': _FUNCAO.get(reg['function_code'], 3),
        'data_type': reg['data_type'],
        'scale': reg['scale'], 'offset': reg['offset'], 'count': reg['register_count'],
    }
```
(Buscar o register do sensor: já há `regs` por profile; mapear `modbus_register_id` → o register. Ajustar o `search_read` dos sensores para incluir `modbus_register_id`, e ler os registers do profile num dict por id.)

- [ ] **Step 5: Rodar e ver passar**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. .venv/bin/python -m pytest api/tests/test_config_serializer.py -q`
Expected: PASS — novos testes + regressão (N4/RS sem `registro`, usa_map do C1 intacto).

- [ ] **Step 6: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add addons/afr_sentinela_sensor_monitor/models/modbus_profile.py api/config_publisher.py api/tests/test_config_serializer.py
git commit -m "feat(config-publish): emite register spec p/ driver generico

Selection ganha 'generico'; serializer emite registro {address,function,
data_type,scale,offset,count} para dispositivos genericos; valida v1
(int16/uint16, count 1) com ConfigInvalida. N4/RS inalterados.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4 (operacional, controller): correção de dados do profile 9

**Files:** nenhum código. Escritas no Odoo vivo.

- [ ] **Step 1: Corrigir os registers do profile 9 (exatidão)**

Register "Temperatura HANKE" (id 10): `register_address` → 1; `scale` → 0.1; `data_type` → int16.
Register "Umidade" (id 53): `register_address` → 0; `scale` → 0.1; `data_type` → uint16.
(Correção de exatidão do dado; NÃO muda o Henke de produção, que usa o driver específico `rs_ws_n01_2d`, ignora o spec. NÃO é o gate — o gate é o teste unitário de decode da Task 1.)

- [ ] **Step 2: Registrar no ledger que o cutover do Henke para genérico fica como passo futuro opcional (não feito).**

---

## Self-Review

**Spec coverage:**
- §Bloco 1 (driver genérico + decode) → Task 1. ✓
- §Bloco 2 (encanamento) → Task 2. ✓
- §Bloco 3 (schema config) → Task 2 Steps 1-3. ✓
- §Bloco 4 (serializer emite registro) → Task 3. ✓
- §Bloco 5 (gate equivalência unitária) → Task 1 Step 1 (vetores 245/0xFFEC/545) + testes por camada em T2/T3. ✓
- §Bloco 6 (correção profile 9) → Task 4. ✓
- §Selection generico → Task 3 Step 1. ✓

**Placeholder scan:** sem TBD; todo código mostrado. O detalhe do `search_read` dos registers no serializer (Task 3 Step 4) está descrito com a fonte (regs por profile) — o implementador mapeia `modbus_register_id`→register.

**Type consistency:** `decode_registro(words, data_type)` (T1) usado nos testes (T1) e chamado por `_read_registro` (T1). `registro` dict `{address,function,data_type,scale,offset,count}` consistente entre config (T2), driver (T1), serializer (T3). `AdaptadorGenerico` (T2) consome `Generico` (T1). `registros` param em `criar_driver` (T2) derivado no leitor (T2).

**Ordem/dependência:** T1 (submódulo, isolado, push+bump) → T2 (hub, precisa do driver) → T3 (serializer + Selection) → T4 (dados, operacional). Sequencial.

**Nota cross-repo:** Task 1 empurra para `github.com/afonsorcarvalho/modbus-connector` main (outward-facing, pré-autorizado). Se `main` divergir do pin `fc70ffb`, PARAR e reportar.
