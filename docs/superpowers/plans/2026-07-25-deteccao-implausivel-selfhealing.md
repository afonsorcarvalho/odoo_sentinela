# Detecção de leitura implausível + self-healing serial — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Marcar leituras fora da faixa física como `suspeito` (em vez de `ok`), reconectar o serial sozinho quando um device entra em falha, e adicionar legenda de colunas ao cabeçalho assinado (schema v3).

**Architecture:** Faixa min/max por sensor no Odoo → publicada pro hub → `leitor` marca `status_leitura="suspeito"` fora dela. `leitor` conta falhas por device e recria o driver (fd serial novo) após N falhas, com teto M e retry a cada K ciclos — params no Odoo por `modbus.device`. Cabeçalho ganha `# colunas:` e `schema_version: 3`; validador aceita v2 e v3. Cadeia de hash intacta (`status_leitura` é campo existente da linha; a legenda é versionada).

**Tech Stack:** Python 3, pytest, Odoo 16 (addon `afr_sentinela_sensor_monitor`), YAML config, Modbus RTU.

## Global Constraints

- `status_leitura` é campo **existente** da linha assinada; usar `suspeito` NÃO muda o formato da linha nem a cadeia de hash. Só o cabeçalho muda (schema v3).
- Faixa (`faixa_min`/`faixa_max`) é **opcional** por sensor: ausente ⇒ sem gate, comportamento atual inalterado (backward-compatible).
- Reconexão nunca pode derrubar o hub: recriar o driver fica dentro do `try` por device; falha ao reabrir → `sensor_offline`, hub sobrevive.
- Defaults dos params de reconexão: `N=3` (falhas seguidas p/ reconectar), `M=5` (teto de reconexões antes de cooldown), `K=10` (ciclos entre re-tentativas no cooldown). Config antiga sem os campos usa esses defaults.
- Arquivos v2 existentes permanecem válidos; o validador aceita v2 e v3.
- Rodar testes: `python -m pytest hub/tests/ contrato/tests/ ingestao/tests/ -q` a partir da raiz. Odoo: `--test-tags /afr_sentinela_sensor_monitor` (nunca a suíte base).

---

### Task 1: Cabeçalho schema v3 com legenda de colunas

**Files:**
- Modify: `contrato/formato.py` (`montar_cabecalho`, linhas 16-35)
- Test: `contrato/tests/test_formato.py`

**Interfaces:**
- Produces: `montar_cabecalho(...)` emite `# schema_version: 3` e uma linha `# colunas: <legenda>` conforme `tipo_arquivo`. A linha entra no cabeçalho canônico (é assinada).

- [ ] **Step 1: Escrever o teste que falha**

```python
def test_cabecalho_v3_tem_schema_e_legenda_de_colunas():
    from contrato import formato
    cab = formato.montar_cabecalho(
        "leituras", "COL-1", "HUB-1", "fp", "2026-07-25", "-03:00", "0.1.0",
        "CLI-1", "SITE-1")
    assert "# schema_version: 3" in cab
    assert ("# colunas: seq|timestamp|sensor_id|area_id|tipo_medida|valor|unidade|"
            "protocolo_origem|status_leitura|cert_ver|cal_ganho|cal_offset|hash|sig") in cab
    # alarmes tem legenda propria
    cab_al = formato.montar_cabecalho(
        "alarmes", "COL-1", "HUB-1", "fp", "2026-07-25", "-03:00", "0.1.0",
        "CLI-1", "SITE-1")
    assert ("# colunas: seq|timestamp|sensor_id|area_id|tipo_medida|tipo_evento|"
            "tipo_violacao|valor|limite_min_vigente|limite_max_vigente|hash|sig") in cab_al
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `python -m pytest contrato/tests/test_formato.py::test_cabecalho_v3_tem_schema_e_legenda_de_colunas -q`
Expected: FAIL (schema_version é 2, sem `# colunas:`).

- [ ] **Step 3: Implementar v3 + legenda**

Em `contrato/formato.py`, substituir o corpo de `montar_cabecalho` (linhas 21-35). Adicionar antes das `linhas` um mapa de legendas e emitir a linha:

```python
_COLUNAS = {
    "leituras": ("seq|timestamp|sensor_id|area_id|tipo_medida|valor|unidade|"
                 "protocolo_origem|status_leitura|cert_ver|cal_ganho|cal_offset|hash|sig"),
    "alarmes": ("seq|timestamp|sensor_id|area_id|tipo_medida|tipo_evento|"
                "tipo_violacao|valor|limite_min_vigente|limite_max_vigente|hash|sig"),
}


def montar_cabecalho(tipo_arquivo, coletor_id, hub_id, pubkey_fingerprint,
                     data_referencia, timezone_offset, firmware_version,
                     cliente_id, site_id):
    for valor in (coletor_id, hub_id, cliente_id, site_id):
        validar_identificador(valor)
    linhas = [
        "# schema_version: 3",
        f"# tipo_arquivo: {tipo_arquivo}",
        f"# cliente_id: {cliente_id}",
        f"# site_id: {site_id}",
        f"# coletor_id: {coletor_id}",
        f"# hub_id: {hub_id}",
        f"# coletor_pubkey_fingerprint: {pubkey_fingerprint}",
        f"# data_referencia: {data_referencia}",
        f"# timezone_offset: {timezone_offset}",
        f"# firmware_version: {firmware_version}",
        f"# colunas: {_COLUNAS[tipo_arquivo]}",
    ]
    if tipo_arquivo == 'leituras':
        linhas.append("# dia_anterior_hash_final: N/A")
    return '\n'.join(linhas) + '\n'
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `python -m pytest contrato/tests/test_formato.py -q`
Expected: PASS (todos; o novo e os existentes).

- [ ] **Step 5: Commit**

```bash
git add contrato/formato.py contrato/tests/test_formato.py
git commit -m "feat(contrato): cabecalho schema v3 com legenda de colunas assinada"
```

---

### Task 2: Validador aceita v3 (legenda) e mantém v2

**Files:**
- Modify: `ingestao/validador.py` (`HEADER_KEYS`, linha 13-17)
- Test: `ingestao/tests/test_validador.py`

**Interfaces:**
- Consumes: cabeçalho v3 com `# colunas:` (Task 1).
- Produces: `_eh_linha_cabecalho` reconhece `colunas` como metadado de cabeçalho; validação de um arquivo v3 completo passa; v2 continua passando.

- [ ] **Step 1: Escrever o teste que falha**

O `# colunas:` precisa ser tratado como cabeçalho (senão vira "corpo" e a validação quebra). Adicionar em `ingestao/tests/test_validador.py` (usar os helpers já existentes no arquivo para montar um arquivo assinado; siga o padrão dos testes de validação ali — monte um arquivo v3 com `formato.montar_cabecalho` e valide):

```python
def test_valida_arquivo_v3_com_legenda_de_colunas(tmp_path):
    # monta um arquivo assinado v3 de 1 leitura e valida sem rejeicao
    # (reutilize o helper de assinatura/registro ja usado nos outros testes
    #  deste arquivo; o ponto e: a linha '# colunas:' nao pode ser tratada
    #  como corpo nem invalidar o arquivo)
    from contrato import formato
    assert formato._eh_linha_cabecalho if False else True  # marcador
    # ... montar arquivo v3, chamar validar_arquivo, assert status != 'invalido'
```

Nota ao implementador: complete o teste montando um arquivo v3 real com os helpers já presentes em `test_validador.py`. O critério é: arquivo v3 (com `# colunas:`) valida com o mesmo status que o equivalente v2, e a linha `# colunas:` conta como cabeçalho.

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `python -m pytest ingestao/tests/test_validador.py -q -k v3`
Expected: FAIL — `# colunas:` cai no corpo → parse/validação quebra.

- [ ] **Step 3: Adicionar `colunas` ao HEADER_KEYS**

Em `ingestao/validador.py`, no set `HEADER_KEYS` (linha 13-17), acrescentar `'colunas'`:

```python
HEADER_KEYS = {
    'schema_version', 'tipo_arquivo', 'cliente_id', 'site_id', 'coletor_id', 'hub_id',
    'coletor_pubkey_fingerprint', 'data_referencia', 'timezone_offset',
    'firmware_version', 'dia_anterior_hash_final', 'hdr_sig', 'colunas',
}
```

- [ ] **Step 4: Rodar e confirmar que passa (v3 e v2)**

Run: `python -m pytest ingestao/tests/test_validador.py -q`
Expected: PASS — todos, incluindo os testes v2 existentes (regressão) e o novo v3.

- [ ] **Step 5: Commit**

```bash
git add ingestao/validador.py ingestao/tests/test_validador.py
git commit -m "feat(ingestao): validador aceita cabecalho v3 (legenda de colunas)"
```

---

### Task 3: Config do hub — faixa por canal + params de reconexão por device

**Files:**
- Modify: `hub/config.py` (`CanalConfig`, `DispositivoConfig`, `_canal`, `carregar_config`)
- Test: `hub/tests/test_config.py`

**Interfaces:**
- Produces:
  - `CanalConfig.faixa_min: float | None`, `CanalConfig.faixa_max: float | None` (default `None`).
  - `DispositivoConfig.reconexao_n: int`, `.reconexao_m: int`, `.reconexao_k: int` (defaults 3/5/10).
  - `_canal` parseia `faixa_min`/`faixa_max` do bruto; `carregar_config` parseia `reconexao_n/m/k` do device (com defaults).

- [ ] **Step 1: Escrever o teste que falha**

```python
def test_canal_parseia_faixa_min_max(tmp_path):
    from hub.config import _canal
    c = _canal({"ch": 1, "sensor_id": "S1", "area_id": "A1",
                "tipo_medida": "umidade_relativa", "unidade": "%RH",
                "faixa_min": 0.1, "faixa_max": 100.0})
    assert c.faixa_min == 0.1 and c.faixa_max == 100.0

def test_canal_sem_faixa_e_none(tmp_path):
    from hub.config import _canal
    c = _canal({"ch": 1, "sensor_id": "S1", "area_id": "A1",
                "tipo_medida": "temperatura", "unidade": "C"})
    assert c.faixa_min is None and c.faixa_max is None
```

E um teste de `carregar_config` para os params do device (montar um YAML mínimo com um device com `reconexao_n/m/k` e outro sem — o sem usa defaults). Siga o padrão dos testes de config existentes em `test_config.py` (há fixtures de config lá).

```python
def test_device_params_reconexao_com_default(tmp_path):
    # device SEM reconexao_* -> defaults 3/5/10
    # device COM reconexao_n=2, reconexao_m=4, reconexao_k=8 -> respeitados
    # (montar YAML com _fixtures_config ou inline; assert nos DispositivoConfig)
    ...
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `python -m pytest hub/tests/test_config.py -q -k "faixa or reconexao"`
Expected: FAIL (`CanalConfig` sem `faixa_min`; `DispositivoConfig` sem `reconexao_n`).

- [ ] **Step 3: Adicionar campos e parse**

Em `hub/config.py`:

`CanalConfig` (após `registro`):
```python
    faixa_min: float = None
    faixa_max: float = None
```

`DispositivoConfig`:
```python
@dataclass
class DispositivoConfig:
    endereco: int
    driver: str
    canais: list = field(default_factory=list)
    reconexao_n: int = 3
    reconexao_m: int = 5
    reconexao_k: int = 10
```

Em `_canal`, no `return CanalConfig(...)`, acrescentar:
```python
        faixa_min=(float(bruto["faixa_min"]) if bruto.get("faixa_min") is not None else None),
        faixa_max=(float(bruto["faixa_max"]) if bruto.get("faixa_max") is not None else None),
```

Em `carregar_config`, no laço de `d in bus["dispositivos"]`, ao criar `DispositivoConfig`:
```python
            dispositivos.append(DispositivoConfig(
                endereco=endereco, driver=driver, canais=canais,
                reconexao_n=int(d.get("reconexao_n", 3)),
                reconexao_m=int(d.get("reconexao_m", 5)),
                reconexao_k=int(d.get("reconexao_k", 10)),
            ))
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `python -m pytest hub/tests/test_config.py -q`
Expected: PASS (novos + regressão).

- [ ] **Step 5: Commit**

```bash
git add hub/config.py hub/tests/test_config.py
git commit -m "feat(hub): config parseia faixa por canal e params de reconexao por device"
```

---

### Task 4: Gate de plausibilidade no leitor (status `suspeito`)

**Files:**
- Modify: `hub/leitor.py` (`ler_todos`, caminho de sucesso, linhas 71-76)
- Test: `hub/tests/test_leitor.py`

**Interfaces:**
- Consumes: `CanalConfig.faixa_min/faixa_max` (Task 3).
- Produces: no caminho de sucesso, valor **corrigido** (pós-calibração) fora de `[faixa_min, faixa_max]` → `status_leitura="suspeito"`, valor real preservado. Sem faixa → `ok` (inalterado).

Nota: a checagem é sobre o valor **corrigido** (o que `_normalizar` grava), não o bruto. Para isso, checar após normalizar. Detalhe abaixo.

- [ ] **Step 1: Escrever o teste que falha**

```python
def test_valor_fora_da_faixa_vira_suspeito():
    # canal com faixa [0.1, 100], driver fake devolve 0.0 -> suspeito
    # canal sem faixa -> ok; canal com valor dentro -> ok
    # (usar o backend/driver fake ja usado em test_leitor.py; montar CanalConfig
    #  com faixa_min/faixa_max; chamar ler_todos; inspecionar status_leitura)
    ...
    assert leitura_henke["status_leitura"] == "suspeito"
    assert leitura_henke["valor"] == 0.0  # valor real preservado
    assert leitura_ok["status_leitura"] == "ok"
```

Siga o padrão de `hub/tests/test_leitor.py` (há um backend/driver fake que devolve valores por canal). Monte um device com um canal de faixa [0.1,100] cujo fake devolve 0.0, e um canal sem faixa.

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `python -m pytest hub/tests/test_leitor.py -q -k suspeito`
Expected: FAIL (hoje 0.0 dentro-do-sucesso vira `ok`).

- [ ] **Step 3: Implementar o gate**

Em `hub/leitor.py`, adicionar um helper e usá-lo no caminho de sucesso. Substituir o bloco de sucesso (linhas 71-76):

```python
                for canal in disp.canais:
                    entrada = por_canal.get(canal.ch)
                    if entrada is None:
                        leituras_disp.append(self._normalizar(canal, 0.0, "erro_leitura", agora))
                    else:
                        norm = self._normalizar(canal, float(entrada["value"]), "ok", agora)
                        if self._fora_da_faixa(canal, norm["valor"]):
                            norm["status_leitura"] = "suspeito"
                        leituras_disp.append(norm)
```

E adicionar o helper (método de `Leitor`):
```python
    @staticmethod
    def _fora_da_faixa(canal, valor):
        if canal.faixa_min is not None and valor < canal.faixa_min:
            return True
        if canal.faixa_max is not None and valor > canal.faixa_max:
            return True
        return False
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `python -m pytest hub/tests/test_leitor.py -q`
Expected: PASS (novos + regressão da resiliência existente).

- [ ] **Step 5: Commit**

```bash
git add hub/leitor.py hub/tests/test_leitor.py
git commit -m "feat(hub): leitor marca leitura fora da faixa como suspeito"
```

---

### Task 5: Self-healing serial no leitor (reconecta após N falhas, teto M, retry K)

**Files:**
- Modify: `hub/leitor.py` (`_DispositivoLigado`, `Leitor.__init__`, `ler_todos`)
- Test: `hub/tests/test_leitor.py`

**Interfaces:**
- Consumes: `DispositivoConfig.reconexao_n/m/k` (Task 3); `criar_driver` (backend).
- Produces: por device, contadores de falha consecutiva; após `N` ciclos "ruins" (qualquer canal `suspeito`/`erro_leitura` ou exceção) → `close()` + recria driver (fd novo). Após `M` reconexões sem um ciclo totalmente `ok` → cooldown: emite `sensor_offline` e só re-tenta reconectar a cada `K` ciclos. Um ciclo totalmente `ok` zera os contadores.

- [ ] **Step 1: Escrever os testes que falham**

Usando o backend/driver fake, cobrir:
1. **Reconecta após N:** fake devolve valor fora-da-faixa (suspeito) por N ciclos → no ciclo N, o leitor chama `close()` no driver e pede um driver novo ao backend (o fake registra a recriação). Assert: houve 1 recriação.
2. **Recupera zera contadores:** após reconectar, fake volta a devolver valor bom → status `ok`, contadores zerados (não reconecta de novo no ciclo seguinte).
3. **Teto M + cooldown K:** fake sempre ruim → após M reconexões, os canais saem `sensor_offline` e não há nova recriação até passar K ciclos; no K-ésimo, tenta recriar de novo.
4. **Reabertura que falha não derruba:** `criar_driver` do fake levanta na recriação → device vira `sensor_offline`, `ler_todos` retorna normalmente (sem exceção propagando).

```python
def test_reconecta_apos_n_falhas_seguidas(): ...
def test_ciclo_ok_zera_contadores_de_reconexao(): ...
def test_teto_m_entra_cooldown_e_retenta_a_cada_k(): ...
def test_falha_ao_recriar_driver_vira_offline_sem_crash(): ...
```

O implementador monta o fake para: (a) contar chamadas de `criar_driver`, (b) contar `close()`, (c) alternar valores bons/ruins por ciclo. Siga o backend fake já existente em `test_leitor.py` e estenda-o.

- [ ] **Step 2: Rodar e confirmar que falham**

Run: `python -m pytest hub/tests/test_leitor.py -q -k "reconecta or cooldown or zera or recriar"`
Expected: FAIL (não há lógica de reconexão hoje).

- [ ] **Step 3: Implementar self-healing**

Em `hub/leitor.py`:

`_DispositivoLigado` passa a guardar o que precisa para recriar e o estado:
```python
class _DispositivoLigado:
    def __init__(self, driver, canais, driver_nome, porta, endereco, recriar, n, m, k):
        self.driver = driver
        self.canais = canais
        self.driver_nome = driver_nome
        self.porta = porta
        self.endereco = endereco
        self.recriar = recriar          # callable() -> novo driver
        self.n, self.m, self.k = n, m, k
        self.falhas_seguidas = 0
        self.reconexoes = 0
        self.cooldown = 0               # >0 = em cooldown, conta ciclos ate retry
```

Em `Leitor.__init__`, ao instanciar o device, montar o `recriar` como closure capturando os mesmos args de `criar_driver`, e passar `n/m/k`:
```python
                def _fazer_recriar(disp=disp, bus=bus, registros=registros):
                    return backend.criar_driver(
                        disp.driver, bus.porta, bus.baud, bus.paridade, bus.stop_bits,
                        disp.endereco, registros=registros,
                    )
                self._dispositivos.append(_DispositivoLigado(
                    driver, disp.canais, disp.driver, bus.porta, disp.endereco,
                    recriar=_fazer_recriar,
                    n=disp.reconexao_n, m=disp.reconexao_m, k=disp.reconexao_k,
                ))
```

Em `ler_todos`, envolver o processamento por device com a máquina de estado. Estrutura (substitui o laço `for disp in self._dispositivos:`):

```python
        for disp in self._dispositivos:
            if disp.cooldown > 0:
                disp.cooldown -= 1
                if disp.cooldown > 0:
                    for canal in disp.canais:
                        leituras.append(self._normalizar(canal, 0.0, "sensor_offline", agora))
                    continue
                # cooldown expirou: tenta recriar antes de ler
                if not self._tentar_recriar(disp):
                    disp.cooldown = disp.k
                    for canal in disp.canais:
                        leituras.append(self._normalizar(canal, 0.0, "sensor_offline", agora))
                    continue

            leituras_disp, ciclo_ruim = self._ler_device(disp, agora)
            leituras.extend(leituras_disp)

            if ciclo_ruim:
                disp.falhas_seguidas += 1
                if disp.falhas_seguidas >= disp.n:
                    disp.falhas_seguidas = 0
                    disp.reconexoes += 1
                    if disp.reconexoes > disp.m:
                        disp.reconexoes = 0
                        disp.cooldown = disp.k
                        print(f"[hub] device em cooldown apos {disp.m} reconexoes: "
                              f"porta={disp.porta} endereco={disp.endereco}")
                    else:
                        self._tentar_recriar(disp)
            else:
                disp.falhas_seguidas = 0
                disp.reconexoes = 0
```

E dois helpers. `_ler_device` extrai o read atual (sucesso→gate, exceção→offline) e devolve `(leituras, ciclo_ruim)` onde `ciclo_ruim` é True se houve exceção OU algum canal `suspeito`/`erro_leitura`:

```python
    def _ler_device(self, disp, agora):
        try:
            lidos = disp.driver.ler(maps=self._specs(disp.canais))
            por_canal = {e["channel"]: e for e in lidos}
            out, ruim = [], False
            for canal in disp.canais:
                entrada = por_canal.get(canal.ch)
                if entrada is None:
                    out.append(self._normalizar(canal, 0.0, "erro_leitura", agora)); ruim = True
                else:
                    norm = self._normalizar(canal, float(entrada["value"]), "ok", agora)
                    if self._fora_da_faixa(canal, norm["valor"]):
                        norm["status_leitura"] = "suspeito"; ruim = True
                    out.append(norm)
            return out, ruim
        except Exception as e:
            if id(disp) not in self._falhados:
                self._falhados.add(id(disp))
                print(f"[hub] leitura falhou: porta={disp.porta} endereco={disp.endereco} erro={e!r}")
            return [self._normalizar(c, 0.0, "sensor_offline", agora) for c in disp.canais], True

    def _tentar_recriar(self, disp):
        try:
            disp.driver.close()
        except Exception:
            pass
        try:
            disp.driver = disp.recriar()
            self._falhados.discard(id(disp))
            print(f"[hub] serial reconectado: porta={disp.porta} endereco={disp.endereco}")
            return True
        except Exception as e:
            print(f"[hub] falha ao reconectar: porta={disp.porta} endereco={disp.endereco} erro={e!r}")
            return False
```

Nota: o bloco `for canais in self._degradados` no fim de `ler_todos` permanece. Remover a lógica antiga de sucesso/exceção inline que foi movida para `_ler_device`.

- [ ] **Step 4: Rodar e confirmar que passam (+ regressão)**

Run: `python -m pytest hub/tests/test_leitor.py -q`
Expected: PASS — novos de reconexão + os de resiliência/gate anteriores.

- [ ] **Step 5: Rodar toda a suíte do hub**

Run: `python -m pytest hub/tests/ contrato/tests/ ingestao/tests/ -q`
Expected: PASS — verde ponta-a-ponta.

- [ ] **Step 6: Commit**

```bash
git add hub/leitor.py hub/tests/test_leitor.py
git commit -m "feat(hub): self-healing serial (reconecta apos N falhas, teto M, retry K)"
```

---

### Task 6: Odoo — campos de faixa no sensor e params de reconexão no device

**Files:**
- Modify: `addons/afr_sentinela_sensor_monitor/models/sensor.py`
- Modify: `addons/afr_sentinela_sensor_monitor/models/modbus_device.py`
- Modify: as views correspondentes (form do sensor e do device) em `addons/afr_sentinela_sensor_monitor/views/`
- Test: `addons/afr_sentinela_sensor_monitor/tests/` (constraint do sensor)

**Interfaces:**
- Produces: `sensor_monitor.sensor.faixa_min`/`faixa_max` (Float, opcionais); constraint `faixa_min < faixa_max` quando ambos setados. `sensor_monitor.modbus.device.reconexao_n/m/k` (Integer, defaults 3/5/10) com constraint `> 0`.

- [ ] **Step 1: Escrever o teste de constraint (TDD Odoo)**

Em `addons/afr_sentinela_sensor_monitor/tests/`, adicionar teste que cria um sensor com `faixa_min >= faixa_max` e espera `ValidationError`; e um com faixa válida que persiste. Siga o padrão dos testes de constraint já existentes no addon (ex.: `_check_slave_address_range`).

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `docker exec odoo_sentinela-odoo-1 odoo -d sentinela --test-enable --test-tags /afr_sentinela_sensor_monitor --stop-after-init --http-port=8169 -u afr_sentinela_sensor_monitor 2>&1 | tail -20`
Expected: FAIL (campos/constraint não existem).

(Confirme o comando de teste do Odoo usado no projeto; porta 8169 para não colidir com 8069/8189.)

- [ ] **Step 3: Adicionar campos + constraints**

`sensor.py` (na classe `Sensor`, junto aos outros fields):
```python
    faixa_min = fields.Float(help="Menor valor fisico plausivel; abaixo disso a leitura e marcada 'suspeito'. Vazio = sem gate.")
    faixa_max = fields.Float(help="Maior valor fisico plausivel; acima disso a leitura e marcada 'suspeito'. Vazio = sem gate.")

    @api.constrains('faixa_min', 'faixa_max')
    def _check_faixa(self):
        for s in self:
            if s.faixa_min and s.faixa_max and s.faixa_min >= s.faixa_max:
                raise ValidationError(_("faixa_min deve ser menor que faixa_max."))
```
(garantir imports `from odoo import api, _` e `from odoo.exceptions import ValidationError`).

Nota sobre `Float` opcional: `fields.Float` default 0.0 não distingue "vazio" de "zero". Para faixa realmente opcional, o serializer (Task 7) trata `0.0/0.0` (ambos zero) como "sem faixa" — documentar. Alternativa mais limpa: campos `faixa_min`/`faixa_max` como `fields.Float` + um booleano `usa_faixa` (análogo a `usa_map`). **Decisão:** usar o booleano `usa_faixa` (default False) para tornar a intenção explícita e evitar ambiguidade do zero. Ajustar o teste, a constraint (só valida se `usa_faixa`) e o serializer de acordo.

`modbus_device.py` (na classe do device):
```python
    reconexao_n = fields.Integer(default=3, help="Falhas seguidas antes de reabrir o serial.")
    reconexao_m = fields.Integer(default=5, help="Teto de reconexoes antes do cooldown.")
    reconexao_k = fields.Integer(default=10, help="Ciclos entre re-tentativas no cooldown.")

    @api.constrains('reconexao_n', 'reconexao_m', 'reconexao_k')
    def _check_reconexao(self):
        for d in self:
            if d.reconexao_n <= 0 or d.reconexao_m <= 0 or d.reconexao_k <= 0:
                raise ValidationError(_("reconexao_n/m/k devem ser > 0."))
```

Adicionar os campos nas views form (sensor e device) para serem editáveis na UI.

- [ ] **Step 4: Rodar e confirmar que passa**

Run: (mesmo comando do Step 2)
Expected: PASS — constraints do sensor e device.

- [ ] **Step 5: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor/
git commit -m "feat(odoo): faixa plausivel no sensor e params de reconexao no device"
```

---

### Task 7: config-publisher serializa faixa e params de reconexão

**Files:**
- Modify: `api/config_publisher.py` (`serializar_config_hub`, montagem do canal ~linha 125 e do dispositivo ~linha 81)
- Test: `api/tests/` (o teste de serialização/round-trip já existente)

**Interfaces:**
- Consumes: campos Odoo da Task 6 (`usa_faixa`/`faixa_min`/`faixa_max` no sensor; `reconexao_n/m/k` no device).
- Produces: canal com `faixa_min`/`faixa_max` quando `usa_faixa`; dispositivo com `reconexao_n/m/k`. Validação: `faixa_min < faixa_max` (senão `ConfigInvalida`).

- [ ] **Step 1: Escrever o teste que falha**

No teste de serialização do config-publisher (siga o arquivo existente que cobre `serializar_config_hub`), adicionar: um sensor com `usa_faixa=True, faixa_min=0.1, faixa_max=100` → o canal serializado tem `faixa_min/faixa_max`; um device com `reconexao_n=2` → o dispositivo serializado carrega `reconexao_n=2` (e m/k default). E `usa_faixa=True` com `faixa_min>=faixa_max` → `ConfigInvalida`.

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `python -m pytest api/tests/ -q -k "faixa or reconexao"`
Expected: FAIL.

- [ ] **Step 3: Implementar a serialização**

Em `api/config_publisher.py`:
- No `search_read` dos sensores (linha ~95-100), acrescentar aos `fields`: `'usa_faixa', 'faixa_min', 'faixa_max'`.
- Na montagem do `canal` (após o bloco de `usa_map`, ~linha 140), acrescentar:
```python
                if s.get('usa_faixa'):
                    if s['faixa_min'] >= s['faixa_max']:
                        raise ConfigInvalida(
                            f"sensor {s['sensor_code']}: usa_faixa=True mas faixa_min "
                            f">= faixa_max ({s['faixa_min']} >= {s['faixa_max']})")
                    canal['faixa_min'] = s['faixa_min']
                    canal['faixa_max'] = s['faixa_max']
```
- No `search_read`/`read` dos devices (linha ~78), acrescentar aos `fields`: `'reconexao_n', 'reconexao_m', 'reconexao_k'`; e no dict `dispositivo` (onde monta cada device), acrescentar:
```python
                'reconexao_n': dev.get('reconexao_n') or 3,
                'reconexao_m': dev.get('reconexao_m') or 5,
                'reconexao_k': dev.get('reconexao_k') or 10,
```
(confirme o nome exato da variável do dict do dispositivo no arquivo).

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `python -m pytest api/tests/ -q`
Expected: PASS (novos + regressão da serialização).

- [ ] **Step 5: Commit**

```bash
git add api/config_publisher.py api/tests/
git commit -m "feat(api): config-publish serializa faixa plausivel e params de reconexao"
```

---

## Self-Review

**Cobertura do spec:**
- Gate de plausibilidade (faixa → `suspeito`) → Tasks 3 (config), 4 (leitor), 6 (Odoo), 7 (publish). ✅
- `status_leitura` += `suspeito` (string livre, sem whitelist) → Task 4 usa; pipeline aceita sem mudança. ✅
- Self-healing (N/M/K, reconecta/teto/cooldown) → Tasks 3 (config), 5 (leitor), 6 (Odoo), 7 (publish). ✅
- Legenda de colunas / schema v3 → Tasks 1 (contrato), 2 (validador). ✅
- Cadeia de hash intacta → Task 1 mantém formato da linha; `suspeito` é campo existente. ✅
- Faixa opcional / backward-compat → `usa_faixa` (Task 6) + defaults (Task 3). ✅

**Placeholders:** Tasks 2, 4, 5, 6, 7 pedem ao implementador completar testes usando fixtures/helpers já existentes nos respectivos arquivos de teste (não há como transcrever esses helpers sem lê-los). Cada uma traz o critério de aceitação explícito e o código de produção completo. Os testes de contrato (Task 1) e config (Task 3) têm código completo.

**Consistência de tipos:** `faixa_min`/`faixa_max` (float|None) em `CanalConfig` (T3) ↔ `_fora_da_faixa` (T4) ↔ serializer (T7) ↔ Odoo `usa_faixa`+floats (T6). `reconexao_n/m/k` (int) em `DispositivoConfig` (T3) ↔ `_DispositivoLigado`/`ler_todos` (T5) ↔ Odoo device (T6) ↔ serializer (T7). Defaults 3/5/10 repetidos consistentes.

## Fora de escopo (follow-up)

- **Exibir `suspeito` no dashboard.** A API de histórico/live devolve pontos `{ts, value}` sem `status_leitura` por ponto; surfacear exige mudança na API + frontend. Separado, próprio design. O dado já cai no Timescale (coluna `status_leitura`), auditável, independente da UI.
- Detecção de "stuck/travado" (N leituras idênticas dentro da faixa) — backlog.
- Cutover do Henke para o driver genérico — assunto do doc de extensibilidade.
- Faixa default por `measurement.type` — evolução futura.
