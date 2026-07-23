# Assinatura ECDSA por Linha + Tenant no Header (B + F) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Elevar o formato de arquivo para `schema_version: 2` — assinar cada linha (ECDSA sobre o hash encadeado, selo no instante da escrita), assinar o header (`hdr_sig`) que semeia a cadeia, gravar `cliente_id`/`site_id` cobertos pela assinatura (F), e carimbar o snapshot de calibração (`cert_ver|cal_ganho|cal_offset`) por leitura — no lado escritor (Hub) e no lado verificador (ingestão).

**Architecture:** O contrato vive em `contrato/formato.py` (escrita) e hoje é **re-implementado** em `ingestao/validador.py` (leitura) — dois lados que precisam mudar em lockstep. Este plano **unifica o validador sobre `contrato.formato`** (mata a classe de bug "format drift") e depois adiciona: `hdr_sig`, `sig` por linha, colunas de calibração, e o caminho `incompleto` (arquivo autêntico linha-a-linha porém sem rodapé — o cenário de durabilidade que justifica B). O Hub aplica a calibração vigente ao valor e carimba os coeficientes; a ingestão caminha a cadeia verificando `hdr_sig` + cada `sig`.

**Tech Stack:** Python 3.9, `cryptography` (ECDSA SECP256R1/SHA256, já em uso), pytest (unit em `contrato/tests`, `hub/tests`, `ingestao/tests`; integração Timescale contra o DB real). Odoo 18 para `file.ledger`.

## Global Constraints

- **1 chave ECDSA (SECP256R1) por device**, hardware-backed no futuro. NUNCA simétrico/HMAC-truncado (mata non-repudiation).
- Cadeia de hash **não atravessa dias**; reinicia por dia. `hash_n = SHA256(hash_{n-1} + linha_sem_hash_sem_sig)` — **inalterado** do canon; `sig_n = ECDSA(priv, hash_n)`.
- Identificadores nunca contêm `|`, `\n`, `\r` (`formato.validar_identificador`) — inclui `cliente_id`/`site_id`.
- **Contrato E→B (deste plano depende):** o config publicado traz, por canal, `'calibracao': {'cert_ver': int, 'ganho': float, 'offset': float}` (Plano E, Task 4). Sem cert vigente → `{0, 1.0, 0.0}` (identidade).
- **Formatação determinística dos coeficientes** (o hash depende do texto exato): `cert_ver` = `str(int(v))`; `cal_ganho`/`cal_offset` = `f"{float(v):.4f}"`.
- `cliente_id` derivado do partner do site: `partner.ref or f"CLI-{partner.id}"` — **mesma fórmula** no publish (api) e no cross-check (ingestão).
- O footer mantém o campo `# assinatura:` (é o `arquivo_sig`/selo de fechamento — ECDSA sobre `hash_final`); não renomear para não rippar validador+ledger sem ganho.
- **Seam B1/B2:** Tasks 1-4 = escritor (produz arquivos v2). Tasks 5-6 = verificador (consome arquivos v2). Cada metade fecha com testes verdes próprios.
- TDD, DRY, YAGNI, commits frequentes.

---

## PARTE B1 — ESCRITOR (contrato + Hub)

### Task 1: `contrato/formato.py` → schema v2 (header tenant + cabeçalho que semeia hdr_sig + linha com coeficientes)

**Files:**
- Modify: `contrato/formato.py`
- Test: `contrato/tests/test_formato.py`

**Interfaces:**
- Produces:
  - `montar_cabecalho(tipo_arquivo, coletor_id, hub_id, pubkey_fingerprint, data_referencia, timezone_offset, firmware_version, cliente_id, site_id)` → string canônica do header **sem** `hdr_sig` (schema_version 2, com `cliente_id`/`site_id`). O `hdr_sig` é anexado pelo chamador após `hash_seed`.
  - `gerar_linha_leitura(hash_anterior, seq, timestamp, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura, cert_ver, cal_ganho, cal_offset)` → `(linha_ate_hash, novo_hash)`; colunas na ordem `seq|ts|sensor|area|tipo|valor|unidade|proto|status|cert_ver|cal_ganho|cal_offset|hash`. O `|sig` é anexado pelo chamador.
  - `fmt_coef(v) -> str` = `f"{float(v):.4f}"`.
- Consumed by: Tasks 3, 4 (Hub) e 5 (validador, via import).

- [ ] **Step 1: Write the failing test**

Adicionar a `contrato/tests/test_formato.py`:

```python
from contrato import formato


def test_cabecalho_v2_tem_tenant_e_schema_2():
    cab = formato.montar_cabecalho(
        'leituras', 'COL-1', 'HUB-1', '9F:3A', '2026-07-16', '-03:00', '2.3.1',
        'CLI-000123', 'SITE-0001')
    assert '# schema_version: 2' in cab
    assert '# cliente_id: CLI-000123' in cab
    assert '# site_id: SITE-0001' in cab
    # hdr_sig NÃO é montado aqui (é anexado pelo escritor após assinar)
    assert 'hdr_sig' not in cab


def test_cliente_site_validam_identificador():
    import pytest
    with pytest.raises(ValueError):
        formato.montar_cabecalho('leituras', 'COL-1', 'HUB-1', 'fp', '2026-07-16',
                                 '-03:00', '2.3.1', 'CLI|BAD', 'SITE-0001')


def test_linha_leitura_carrega_coeficientes_de_calibracao():
    seed = formato.hash_seed('# cab\n')
    linha, novo_hash = formato.gerar_linha_leitura(
        seed, 1, '2026-07-16T00:01:00-03:00', 'SNR-1', 'EXPURGO', 'temperatura',
        130.60, 'C', '4-20ma', 'ok', 3, 0.965, 0.33)
    campos = linha.split('|')
    # seq|ts|sensor|area|tipo|valor|unidade|proto|status|cert_ver|cal_ganho|cal_offset|hash
    assert campos[9] == '3'
    assert campos[10] == '0.9650'
    assert campos[11] == '0.3300'
    assert campos[-1] == novo_hash
    # hash cobre os coeficientes: recomputar com o mesmo prefixo bate
    sem_hash = '|'.join(campos[:-1])
    assert formato.hash_linha(seed, sem_hash) == novo_hash
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest contrato/tests/test_formato.py -q`
Expected: FAIL — `montar_cabecalho()` recebe argumentos demais / `gerar_linha_leitura()` argumentos demais.

- [ ] **Step 3: Write minimal implementation**

Em `contrato/formato.py`, substituir `montar_cabecalho` e `gerar_linha_leitura`, e adicionar `fmt_coef`:

```python
def montar_cabecalho(tipo_arquivo, coletor_id, hub_id, pubkey_fingerprint,
                     data_referencia, timezone_offset, firmware_version,
                     cliente_id, site_id):
    for valor in (coletor_id, hub_id, cliente_id, site_id):
        validar_identificador(valor)
    linhas = [
        "# schema_version: 2",
        f"# tipo_arquivo: {tipo_arquivo}",
        f"# cliente_id: {cliente_id}",
        f"# site_id: {site_id}",
        f"# coletor_id: {coletor_id}",
        f"# hub_id: {hub_id}",
        f"# coletor_pubkey_fingerprint: {pubkey_fingerprint}",
        f"# data_referencia: {data_referencia}",
        f"# timezone_offset: {timezone_offset}",
        f"# firmware_version: {firmware_version}",
    ]
    if tipo_arquivo == 'leituras':
        linhas.append("# dia_anterior_hash_final: N/A")
    return '\n'.join(linhas) + '\n'


def fmt_coef(valor):
    return f"{float(valor):.4f}"


def gerar_linha_leitura(hash_anterior, seq, timestamp, sensor_id, area_id, tipo_medida,
                        valor, unidade, protocolo_origem, status_leitura,
                        cert_ver, cal_ganho, cal_offset):
    for identificador in (sensor_id, area_id):
        validar_identificador(identificador)
    campos_sem_hash = [
        str(seq), timestamp, sensor_id, area_id, tipo_medida, str(valor), unidade,
        protocolo_origem, status_leitura,
        str(int(cert_ver)), fmt_coef(cal_ganho), fmt_coef(cal_offset),
    ]
    linha_sem_hash = '|'.join(campos_sem_hash)
    novo_hash = hash_linha(hash_anterior, linha_sem_hash)
    return linha_sem_hash + '|' + novo_hash, novo_hash
```

> `gerar_linha_alarme` **não muda de colunas** (§4.3 restringe os coeficientes às leituras). O `sig` por linha de alarme é anexado pelo chamador, igual às leituras. O header de alarme já ganha `cliente_id`/`site_id` de graça (mesmo `montar_cabecalho`).

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && python -m pytest contrato/tests/test_formato.py -q`
Expected: PASS. (Os testes antigos de `montar_cabecalho`/`gerar_linha_leitura` que passavam menos argumentos vão quebrar — **atualize-os** para a nova assinatura no mesmo passo; são chamadas diretas, adicionar `cliente_id`/`site_id` e `cert_ver, cal_ganho, cal_offset`.)

- [ ] **Step 5: Commit**

```bash
git add contrato/formato.py contrato/tests/test_formato.py
git commit -m "feat(formato): schema v2 — header tenant + coeficientes de calibracao por linha"
```

---

### Task 2: Publicar `cliente_id`/`site_id` no config (F) + Hub config parseia tenant e calibração por canal

**Files:**
- Modify: `api/config_publisher.py` (emitir `cliente_id`/`site_id` no topo do config)
- Modify: `hub/config.py` (`HubConfig.cliente_id`/`site_id`; `CanalConfig.calibracao`; parse)
- Test: `api/tests/test_config_serializer.py`, `hub/tests/test_config.py`

**Interfaces:**
- Consumes: `canal['calibracao']` (Plano E, Task 4); `site.partner_id`, `site.site_code`.
- Produces:
  - config publicado ganha topo `'cliente_id': str`, `'site_id': str`.
  - `HubConfig` ganha `cliente_id: str`, `site_id: str`.
  - `CanalConfig` ganha `calibracao: dict` = `{'cert_ver', 'ganho', 'offset'}`.

- [ ] **Step 1: Write the failing tests**

Em `api/tests/test_config_serializer.py`:

```python
def test_config_traz_tenant_no_topo():
    from ingestao import odoo_cliente
    from api.config_publisher import serializar_config_hub
    from api.odoo import get_cliente_servico
    cliente = get_cliente_servico()
    hub_code = _prov_hub_modbus(cliente)
    cfg = serializar_config_hub(cliente, hub_code)
    assert cfg['site_id']  # site_code do site do hub
    assert cfg['cliente_id']  # partner.ref ou CLI-<id>
```

Em `hub/tests/test_config.py` (segue o estilo de `_fixtures_config.py`; adicione as chaves ao YAML de fixture):

```python
def test_hubconfig_carrega_tenant_e_calibracao_do_canal(tmp_path):
    from hub import config as config_mod
    yaml_txt = """
hub_id: HUB-1
coletor_id: COL-1
cliente_id: CLI-000123
site_id: SITE-0001
firmware_version: 2.3.1
timezone_offset: "-03:00"
intervalo_leitura_s: 60
caminho_chave: /tmp/k.pem
caminho_dados: /tmp/dados
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
            sensor_id: SNR-1
            area_id: EXPURGO
            tipo_medida: temperatura
            unidade: C
            protocolo_origem: 4-20ma
            map: {in: [4, 20], out: [0, 150]}
            calibracao: {cert_ver: 3, ganho: 0.965, offset: 0.33}
"""
    p = tmp_path / "config.yaml"
    p.write_text(yaml_txt)
    cfg = config_mod.carregar_config(str(p))
    assert cfg.cliente_id == 'CLI-000123'
    assert cfg.site_id == 'SITE-0001'
    canal = cfg.barramentos[0].dispositivos[0].canais[0]
    assert canal.calibracao == {'cert_ver': 3, 'ganho': 0.965, 'offset': 0.33}


def test_canal_sem_calibracao_usa_identidade(tmp_path):
    from hub import config as config_mod
    yaml_txt = """
hub_id: HUB-1
coletor_id: COL-1
cliente_id: CLI-1
site_id: SITE-1
firmware_version: 2.3.1
timezone_offset: "-03:00"
intervalo_leitura_s: 60
caminho_chave: /tmp/k.pem
caminho_dados: /tmp/dados
barramentos:
  - porta: /dev/ttyUSB0
    baud: 9600
    paridade: N
    stop_bits: 1
    dispositivos:
      - endereco: 1
        driver: n4aib16
        canais:
          - {ch: 1, sensor_id: SNR-1, area_id: EXPURGO, tipo_medida: temperatura,
             unidade: C, protocolo_origem: 4-20ma, map: {in: [4, 20], out: [0, 150]}}
"""
    p = tmp_path / "config.yaml"
    p.write_text(yaml_txt)
    cfg = config_mod.carregar_config(str(p))
    canal = cfg.barramentos[0].dispositivos[0].canais[0]
    assert canal.calibracao == {'cert_ver': 0, 'ganho': 1.0, 'offset': 0.0}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest hub/tests/test_config.py -q api/tests/test_config_serializer.py::test_config_traz_tenant_no_topo -q`
Expected: FAIL — `HubConfig` sem `cliente_id`; `cfg['site_id']` KeyError.

- [ ] **Step 3: Write minimal implementation**

(a) `hub/config.py` — adicionar campos aos dataclasses:

```python
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
    calibracao: dict = None
```

Em `HubConfig`, adicionar após `coletor_id: str`:

```python
    cliente_id: str = ''
    site_id: str = ''
```

Em `_canal(bruto)`, antes do `return`, resolver calibração com default identidade:

```python
    cal = bruto.get("calibracao") or {}
    calibracao = {
        'cert_ver': int(cal.get('cert_ver', 0)),
        'ganho': float(cal.get('ganho', 1.0)),
        'offset': float(cal.get('offset', 0.0)),
    }
```

e passar `calibracao=calibracao` no `CanalConfig(...)`.

Em `carregar_config`, no `return HubConfig(...)`, adicionar:

```python
        cliente_id=dados.get("cliente_id", ""), site_id=dados.get("site_id", ""),
```

(b) `api/config_publisher.py` — no `return` de `serializar_config_hub`, resolver o site/partner e emitir tenant. Antes do `return`, após montar `barramentos`:

```python
    site_row = ex('sensor_monitor.hub', 'read', [hub['id']], fields=['site_id'])[0]
    site_odoo_id = site_row['site_id'][0]
    site = ex('sensor_monitor.site', 'read', [site_odoo_id],
              fields=['site_code', 'partner_id'])[0]
    partner_id = site['partner_id'][0]
    partner = ex('res.partner', 'read', [partner_id], fields=['ref'])[0]
    cliente_id = partner.get('ref') or f"CLI-{partner_id}"
```

e no dict de retorno adicionar:

```python
        'cliente_id': cliente_id,
        'site_id': site['site_code'],
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest hub/tests/test_config.py api/tests/test_config_serializer.py -q`
Expected: PASS (todos, incl. regressão).

- [ ] **Step 5: Commit**

```bash
git add hub/config.py api/config_publisher.py hub/tests/test_config.py api/tests/test_config_serializer.py
git commit -m "feat(config): tenant no topo + calibracao por canal (F publish + hub parse)"
```

---

### Task 3: Hub `leitor` — aplicar calibração vigente ao valor e carimbar coeficientes na leitura

**Files:**
- Modify: `hub/leitor.py` (`_normalizar` aplica `ganho*nominal+offset` e injeta `cert_ver`/`cal_ganho`/`cal_offset`)
- Test: `hub/tests/test_leitor.py`

**Interfaces:**
- Consumes: `CanalConfig.calibracao` (Task 2).
- Produces: cada `leitura` dict ganha `'cert_ver': int`, `'cal_ganho': float`, `'cal_offset': float`; `'valor'` passa a ser o **valor corrigido** (`ganho*nominal + offset`). Consumido pela Task 4 (arquivo_diario).

- [ ] **Step 1: Write the failing test**

Adicionar a `hub/tests/test_leitor.py` (usa o backend fake do módulo; veja os testes existentes para o construtor de fixture — reutilize o padrão de canal com `calibracao`):

```python
def test_normalizar_aplica_calibracao_e_carimba_coeficientes():
    from hub.config import CanalConfig
    from hub.leitor import Leitor
    canal = CanalConfig(
        ch=1, sensor_id='SNR-1', area_id='EXPURGO', tipo_medida='temperatura',
        unidade='C', protocolo_origem='4-20ma', map_in=(4, 20), map_out=(0, 150),
        calibracao={'cert_ver': 3, 'ganho': 0.965, 'offset': 0.33})
    # nominal (já mapeado pelo backend) = 100.0 → corrigido = 0.965*100 + 0.33 = 96.83
    leitura = Leitor._normalizar(object.__new__(Leitor), canal, 100.0, 'ok', 'AGORA')
    assert leitura['cert_ver'] == 3
    assert leitura['cal_ganho'] == 0.965
    assert leitura['cal_offset'] == 0.33
    assert abs(leitura['valor'] - 96.83) < 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest hub/tests/test_leitor.py::test_normalizar_aplica_calibracao_e_carimba_coeficientes -q`
Expected: FAIL — `KeyError: 'cert_ver'` / `valor` não corrigido.

- [ ] **Step 3: Write minimal implementation**

Em `hub/leitor.py`, substituir `_normalizar`:

```python
    def _normalizar(self, canal, valor, status, agora):
        cal = canal.calibracao or {'cert_ver': 0, 'ganho': 1.0, 'offset': 0.0}
        corrigido = cal['ganho'] * valor + cal['offset']
        return {
            "timestamp": agora, "sensor_id": canal.sensor_id, "area_id": canal.area_id,
            "tipo_medida": canal.tipo_medida, "valor": corrigido, "unidade": canal.unidade,
            "protocolo_origem": canal.protocolo_origem, "status_leitura": status,
            "cert_ver": cal['cert_ver'], "cal_ganho": cal['ganho'], "cal_offset": cal['offset'],
        }
```

> Nota: em status de erro (`erro_leitura`/`sensor_offline`), o valor cru é `0.0`; a calibração ainda é carimbada (rastreabilidade do coeficiente vigente naquele instante). O valor corrigido de `0.0` é `offset` — aceitável (status já sinaliza que não é leitura boa).

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && python -m pytest hub/tests/test_leitor.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add hub/leitor.py hub/tests/test_leitor.py
git commit -m "feat(leitor): aplica calibracao vigente e carimba cert_ver/ganho/offset"
```

---

### Task 4: Hub `arquivo_diario` — escrever v2 (hdr_sig, sig por linha, footer arquivo_sig)

**Files:**
- Modify: `hub/arquivo_diario.py` (header assinado; colunas de calibração + `sig` por linha; `reconstruir_estado` tira hash+sig)
- Modify: `hub/main.py` (passar `cliente_id`/`site_id` ao construir `ArquivoDiario`)
- Test: `hub/tests/test_arquivo_diario.py`

**Interfaces:**
- Consumes: `formato.montar_cabecalho`/`gerar_linha_leitura` (Task 1); `leitura` com coeficientes (Task 3); `HubConfig.cliente_id`/`site_id` (Task 2); `assinador.assinar` (existente).
- Produces: arquivo `.txt` v2 no disco — header + `# hdr_sig:`, linhas terminando em `|hash|sig`, footer `# total_linhas/# hash_final/# assinatura`. Consumido pela Parte B2 (validador).

- [ ] **Step 1: Write the failing test**

Adicionar a `hub/tests/test_arquivo_diario.py` (reutilize o `AssinadorSoftware` de fixture dos testes existentes; ajuste o construtor conforme o padrão do arquivo):

```python
from datetime import datetime

from contrato import formato


def _leitura(ts):
    return {'timestamp': ts, 'sensor_id': 'SNR-1', 'area_id': 'EXPURGO',
            'tipo_medida': 'temperatura', 'valor': 96.83, 'unidade': 'C',
            'protocolo_origem': '4-20ma', 'status_leitura': 'ok',
            'cert_ver': 3, 'cal_ganho': 0.965, 'cal_offset': 0.33}


def test_arquivo_v2_tem_hdr_sig_e_sig_por_linha(tmp_path, assinador):
    from hub.arquivo_diario import ArquivoDiario
    arq = ArquivoDiario('COL-1', 'HUB-1', '2.3.1', '-03:00', str(tmp_path), assinador,
                        cliente_id='CLI-1', site_id='SITE-1')
    arq.registrar(_leitura(datetime(2026, 7, 16, 0, 1, 0)))
    arq.registrar(_leitura(datetime(2026, 7, 16, 0, 2, 0)))
    texto = arq.caminho('2026-07-16').read_text()
    linhas = [l for l in texto.split('\n') if l]

    assert '# schema_version: 2' in texto
    assert any(l.startswith('# hdr_sig: ') for l in linhas)

    corpo = [l for l in linhas if not l.startswith('#')]
    assert len(corpo) == 2
    # 14 colunas: ...|cert_ver|cal_ganho|cal_offset|hash|sig
    campos = corpo[0].split('|')
    assert len(campos) == 14
    assert campos[9] == '3' and campos[10] == '0.9650' and campos[11] == '0.3300'
    # cada linha tem sig != vazio
    assert corpo[0].split('|')[-1]
    assert corpo[1].split('|')[-1]


def test_reconstruir_estado_ignora_hdr_sig_e_tira_hash_e_sig(tmp_path, assinador):
    from hub.arquivo_diario import ArquivoDiario, reconstruir_estado
    arq = ArquivoDiario('COL-1', 'HUB-1', '2.3.1', '-03:00', str(tmp_path), assinador,
                        cliente_id='CLI-1', site_id='SITE-1')
    arq.registrar(_leitura(datetime(2026, 7, 16, 0, 1, 0)))
    texto = arq.caminho('2026-07-16').read_text()
    hash_estado, prox_seq = reconstruir_estado(texto)
    # o hash de estado deve casar com o hash da última linha (campo -2)
    corpo = [l for l in texto.split('\n') if l and not l.startswith('#')]
    assert hash_estado == corpo[-1].split('|')[-2]
    assert prox_seq == 2
```

> Este teste assume uma fixture `assinador` (pytest) que devolve um `AssinadorSoftware` com chave temporária. Se o arquivo de teste ainda não a tiver, adicione:
> ```python
> import pytest
> from hub.assinador import AssinadorSoftware
> @pytest.fixture
> def assinador(tmp_path):
>     return AssinadorSoftware(str(tmp_path / "chave.pem"))
> ```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest hub/tests/test_arquivo_diario.py -q`
Expected: FAIL — `ArquivoDiario.__init__` não aceita `cliente_id`/`site_id`; sem `hdr_sig`; linha com 11 colunas.

- [ ] **Step 3: Write minimal implementation**

Em `hub/arquivo_diario.py`:

(a) `reconstruir_estado` — excluir `hdr_sig` do seed e tirar 2 campos (hash+sig):

```python
def reconstruir_estado(texto):
    """A partir do conteúdo (cabeçalho + hdr_sig + N linhas, sem rodapé),
    devolve (hash_atual, proximo_seq)."""
    linhas = [l for l in texto.split("\n") if l != ""]
    cabecalho = [l for l in linhas
                 if l.startswith("#") and not l.startswith("# hdr_sig:")]
    corpo = [l for l in linhas if not l.startswith("#")]
    hash_atual = formato.hash_seed("\n".join(cabecalho) + "\n")
    for linha in corpo:
        sem_hash = linha.rsplit("|", 2)[0]  # tira hash E sig
        hash_atual = formato.hash_linha(hash_atual, sem_hash)
    return hash_atual, len(corpo) + 1
```

(b) `__init__` — aceitar tenant:

```python
    def __init__(self, coletor_id, hub_id, firmware_version, timezone_offset,
                 caminho_dados, assinador, cliente_id='', site_id=''):
        self._coletor_id = coletor_id
        self._hub_id = hub_id
        self._firmware = firmware_version
        self._tz_offset = timezone_offset
        self._cliente_id = cliente_id
        self._site_id = site_id
        self._dir = Path(caminho_dados).expanduser() / coletor_id
        self._assinador = assinador
        self._data_atual = None
        self._hash = None
        self._seq = 1
```

(c) `_abrir` — montar header v2 e anexar `hdr_sig` (assina o seed):

```python
    def _abrir(self, data_referencia):
        self._dir.mkdir(parents=True, exist_ok=True)
        caminho = self.caminho(data_referencia)
        if caminho.exists():
            self._hash, self._seq = reconstruir_estado(caminho.read_text())
        else:
            cabecalho = formato.montar_cabecalho(
                "leituras", self._coletor_id, self._hub_id,
                self._assinador.fingerprint(), data_referencia,
                self._tz_offset, self._firmware, self._cliente_id, self._site_id,
            )
            self._hash = formato.hash_seed(cabecalho)
            hdr_sig = base64.b64encode(self._assinador.assinar(self._hash.encode())).decode()
            caminho.write_text(cabecalho + f"# hdr_sig: {hdr_sig}\n")
            self._seq = 1
        self._data_atual = data_referencia
```

(d) `registrar` — passar coeficientes e anexar `sig`:

```python
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
            leitura["cert_ver"], leitura["cal_ganho"], leitura["cal_offset"],
        )
        sig = base64.b64encode(self._assinador.assinar(self._hash.encode())).decode()
        with self.caminho(data_referencia).open("a") as fh:
            fh.write(linha + "|" + sig + "\n")
        self._seq += 1
```

> `selar()` não muda: `reconstruir_estado` (agora v2-aware) devolve `hash_final`; assina e escreve o footer `# assinatura:` (o `arquivo_sig`). `recuperar_pendentes` e `_esta_selado` também ficam iguais.

(e) `hub/main.py` — passar tenant ao construir (linha ~87):

```python
    arquivo = ArquivoDiario(cfg.coletor_id, cfg.hub_id, cfg.firmware_version,
                            cfg.timezone_offset, cfg.caminho_dados, assinador,
                            cliente_id=cfg.cliente_id, site_id=cfg.site_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && python -m pytest hub/tests/ -q`
Expected: PASS (todos os testes do hub, incl. os antigos de arquivo_diario — atualize os que construíam leitura sem os coeficientes: adicione `cert_ver/cal_ganho/cal_offset` aos dicts de fixture).

- [ ] **Step 5: Commit**

```bash
git add hub/arquivo_diario.py hub/main.py hub/tests/test_arquivo_diario.py
git commit -m "feat(arquivo_diario): escreve v2 — hdr_sig + sig por linha + coeficientes"
```

---

## PARTE B2 — VERIFICADOR (ingestão)

### Task 5: `ingestao/validador` — unificar sobre `contrato.formato`, verificar hdr_sig + sig por linha, caminho `incompleto`

**Files:**
- Modify: `ingestao/validador.py`
- Test: `ingestao/tests/test_validador.py`

**Interfaces:**
- Consumes: `contrato.formato.hash_seed`/`hash_linha` (unificação — para de re-implementar); arquivos v2 (Task 4); `registro_coletores.obter_chave_publica` (existente).
- Produces: `validar_arquivo(caminho, registro_path)` → `ResultadoValidacao` com `status_validacao ∈ {valido, incompleto, invalido}`, agora com `cliente_id`/`site_id`/`pubkey_fingerprint` populados. `incompleto` = header+linhas autênticas mas **sem footer** (crash não-recuperado). Consumido pela Task 6 (ingestor).

- [ ] **Step 1: Write the failing test**

Adicionar a `ingestao/tests/test_validador.py` (reutilize helpers de escrita dos testes existentes; se não houver, gere o arquivo com `ArquivoDiario` + registre a pubkey via `registro_coletores`):

```python
import base64
from datetime import datetime

from hub.arquivo_diario import ArquivoDiario
from hub.assinador import AssinadorSoftware
from ingestao import registro_coletores, validador


def _leitura(ts, valor=96.83):
    return {'timestamp': ts, 'sensor_id': 'SNR-1', 'area_id': 'EXPURGO',
            'tipo_medida': 'temperatura', 'valor': valor, 'unidade': 'C',
            'protocolo_origem': '4-20ma', 'status_leitura': 'ok',
            'cert_ver': 3, 'cal_ganho': 0.965, 'cal_offset': 0.33}


def _preparar(tmp_path, selar=True):
    assinador = AssinadorSoftware(str(tmp_path / "k.pem"))
    arq = ArquivoDiario('COL-1', 'HUB-1', '2.3.1', '-03:00', str(tmp_path / "d"),
                        assinador, cliente_id='CLI-1', site_id='SITE-1')
    arq.registrar(_leitura(datetime(2026, 7, 16, 0, 1, 0)))
    arq.registrar(_leitura(datetime(2026, 7, 16, 0, 2, 0)))
    if selar:
        arq.selar('2026-07-16')
    registro = str(tmp_path / "reg.json")
    registro_coletores.registrar_coletor(registro, 'COL-1', assinador.chave_publica_pem())
    return arq.caminho('2026-07-16'), registro


def test_arquivo_v2_selado_valido(tmp_path):
    caminho, registro = _preparar(tmp_path, selar=True)
    r = validador.validar_arquivo(str(caminho), registro)
    assert r.status_validacao == 'valido'
    assert r.total_linhas == 2
    assert r.cliente_id == 'CLI-1' and r.site_id == 'SITE-1'


def test_arquivo_sem_rodape_e_incompleto(tmp_path):
    caminho, registro = _preparar(tmp_path, selar=False)  # crash: sem footer
    r = validador.validar_arquivo(str(caminho), registro)
    assert r.status_validacao == 'incompleto'
    assert len(r.leituras) == 2  # aceita linhas verificadas até a última sig válida


def test_sig_de_linha_adulterada_rejeita(tmp_path):
    caminho, registro = _preparar(tmp_path, selar=True)
    linhas = caminho.read_text().split('\n')
    corpo_idx = next(i for i, l in enumerate(linhas) if l and not l.startswith('#'))
    campos = linhas[corpo_idx].split('|')
    campos[5] = '999.99'  # adultera o valor, mantém hash/sig antigos
    linhas[corpo_idx] = '|'.join(campos)
    caminho.write_text('\n'.join(linhas))
    r = validador.validar_arquivo(str(caminho), registro)
    assert r.status_validacao == 'invalido'


def test_hdr_sig_adulterado_rejeita(tmp_path):
    caminho, registro = _preparar(tmp_path, selar=True)
    linhas = caminho.read_text().split('\n')
    i = next(i for i, l in enumerate(linhas) if l.startswith('# cliente_id:'))
    linhas[i] = '# cliente_id: CLI-OUTRO'  # muda header coberto pelo hdr_sig
    caminho.write_text('\n'.join(linhas))
    r = validador.validar_arquivo(str(caminho), registro)
    assert r.status_validacao == 'invalido'
    assert 'header' in (r.motivo_rejeicao or '').lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest ingestao/tests/test_validador.py -q`
Expected: FAIL — sem verificação de `hdr_sig`; parse quebra em 14 colunas; sem status `incompleto`.

- [ ] **Step 3: Write minimal implementation**

Reescrever `ingestao/validador.py` (unificado sobre `contrato.formato`):

```python
import base64
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from contrato import formato
from . import registro_coletores

HEADER_KEYS = {
    'schema_version', 'tipo_arquivo', 'cliente_id', 'site_id', 'coletor_id', 'hub_id',
    'coletor_pubkey_fingerprint', 'data_referencia', 'timezone_offset',
    'firmware_version', 'dia_anterior_hash_final', 'hdr_sig',
}


@dataclass
class ResultadoValidacao:
    status_validacao: str
    motivo_rejeicao: str
    total_linhas: int
    coletor_id: str
    data_referencia: str = None
    hash_final: str = None
    assinatura: str = None
    tipo_arquivo: str = None
    cliente_id: str = None
    site_id: str = None
    pubkey_fingerprint: str = None
    leituras: list = field(default_factory=list)
    eventos: list = field(default_factory=list)


def _parse_bloco_metadados(linhas):
    metadados = {}
    for linha in linhas:
        if not linha.startswith('#'):
            continue
        chave, _, valor = linha[2:].partition(':')
        metadados[chave.strip()] = valor.strip()
    return metadados


def _eh_linha_cabecalho(linha):
    if not linha.startswith('#'):
        return False
    chave, _, _ = linha[2:].partition(':')
    return chave.strip() in HEADER_KEYS


def parse_arquivo(texto):
    linhas = texto.split('\n')
    if linhas and linhas[-1] == '':
        linhas = linhas[:-1]
    idx = 0
    linhas_cabecalho = []
    while idx < len(linhas) and _eh_linha_cabecalho(linhas[idx]):
        linhas_cabecalho.append(linhas[idx])
        idx += 1
    linhas_corpo = []
    while idx < len(linhas) and not linhas[idx].startswith('#'):
        linhas_corpo.append(linhas[idx])
        idx += 1
    linhas_rodape = linhas[idx:]
    # canônico do header = tudo menos a linha hdr_sig (que assina esse canônico)
    canonico = [l for l in linhas_cabecalho if not l.startswith('# hdr_sig:')]
    cabecalho_canonico = '\n'.join(canonico) + '\n'
    metadados_cabecalho = _parse_bloco_metadados(linhas_cabecalho)
    metadados_rodape = _parse_bloco_metadados(linhas_rodape)
    return metadados_cabecalho, cabecalho_canonico, linhas_corpo, metadados_rodape


def parse_linha_leitura(linha):
    campos = linha.split('|')
    (seq, timestamp, sensor_id, area_id, tipo_medida, valor, unidade,
     protocolo_origem, status_leitura, cert_ver, cal_ganho, cal_offset,
     hash_linha, sig) = campos
    return {
        'seq': int(seq), 'timestamp': timestamp, 'sensor_id': sensor_id,
        'area_id': area_id, 'tipo_medida': tipo_medida, 'valor': float(valor),
        'unidade': unidade, 'protocolo_origem': protocolo_origem,
        'status_leitura': status_leitura, 'cert_ver': int(cert_ver),
        'cal_ganho': float(cal_ganho), 'cal_offset': float(cal_offset),
        'hash': hash_linha, 'sig': sig, 'linha_sem_hash': '|'.join(campos[:-2]),
    }


def parse_linha_alarme(linha):
    campos = linha.split('|')
    (seq, timestamp, sensor_id, area_id, tipo_medida, tipo_evento, tipo_violacao,
     valor, limite_min_vigente, limite_max_vigente, hash_linha, sig) = campos
    return {
        'seq': int(seq), 'timestamp': timestamp, 'sensor_id': sensor_id,
        'area_id': area_id, 'tipo_medida': tipo_medida, 'tipo_evento': tipo_evento,
        'tipo_violacao': tipo_violacao, 'valor': float(valor),
        'limite_min_vigente': None if limite_min_vigente == '—' else float(limite_min_vigente),
        'limite_max_vigente': None if limite_max_vigente == '—' else float(limite_max_vigente),
        'hash': hash_linha, 'sig': sig, 'linha_sem_hash': '|'.join(campos[:-2]),
    }


def _verificar_sig(chave_publica, sig_b64, hash_hex):
    chave_publica.verify(base64.b64decode(sig_b64), hash_hex.encode(),
                         ec.ECDSA(hashes.SHA256()))


def validar_arquivo(caminho, registro_path):
    texto = Path(caminho).read_text()
    metadados_cab, cabecalho_canonico, linhas_corpo, metadados_rod = parse_arquivo(texto)
    coletor_id = metadados_cab.get('coletor_id')
    tipo_arquivo = metadados_cab.get('tipo_arquivo')
    hash_final_declarado = metadados_rod.get('hash_final')
    assinatura_declarada = metadados_rod.get('assinatura')

    def _res(status, motivo, leituras=None, total=None):
        r = ResultadoValidacao(
            status_validacao=status, motivo_rejeicao=motivo,
            total_linhas=total if total is not None else len(linhas_corpo),
            coletor_id=coletor_id, data_referencia=metadados_cab.get('data_referencia'),
            hash_final=hash_final_declarado, assinatura=assinatura_declarada,
            tipo_arquivo=tipo_arquivo, cliente_id=metadados_cab.get('cliente_id'),
            site_id=metadados_cab.get('site_id'),
            pubkey_fingerprint=metadados_cab.get('coletor_pubkey_fingerprint'))
        if leituras is not None:
            if tipo_arquivo == 'alarmes':
                r.eventos = leituras
            else:
                r.leituras = leituras
        return r

    try:
        chave_publica = registro_coletores.obter_chave_publica(registro_path, coletor_id)
    except KeyError as exc:
        return _res('invalido', str(exc))

    # 1. hdr_sig semeia a cadeia
    hash_atual = formato.hash_seed(cabecalho_canonico)
    hdr_sig = metadados_cab.get('hdr_sig')
    if not hdr_sig:
        return _res('invalido', 'header sem hdr_sig (schema v2 exige header assinado)')
    try:
        _verificar_sig(chave_publica, hdr_sig, hash_atual)
    except InvalidSignature:
        return _res('invalido', 'assinatura do header (hdr_sig) inválida')

    # 2. caminha a cadeia, verificando hash + sig por linha
    parse_linha = parse_linha_alarme if tipo_arquivo == 'alarmes' else parse_linha_leitura
    validas = []
    for linha in linhas_corpo:
        try:
            parsed = parse_linha(linha)
        except ValueError:
            break  # linha malformada (cauda truncada por crash)
        hash_esperado = formato.hash_linha(hash_atual, parsed['linha_sem_hash'])
        if hash_esperado != parsed['hash']:
            break
        try:
            _verificar_sig(chave_publica, parsed['sig'], parsed['hash'])
        except InvalidSignature:
            break
        hash_atual = hash_esperado
        validas.append(parsed)

    tem_footer = hash_final_declarado is not None
    quebrou_cedo = len(validas) < len(linhas_corpo)

    # 3. decidir status
    if tem_footer:
        if quebrou_cedo:
            return _res('invalido',
                        f'cadeia/sig quebrada na linha seq={len(validas) + 1}', total=len(linhas_corpo))
        if hash_atual != hash_final_declarado:
            return _res('invalido', 'hash_final do rodapé não bate com a cadeia recalculada')
        try:
            _verificar_sig(chave_publica, assinatura_declarada, hash_final_declarado)
        except InvalidSignature:
            return _res('invalido', 'assinatura do arquivo (footer) inválida')
        return _res('valido', None, leituras=validas, total=len(validas))

    # sem footer: autêntico até a última sig válida, porém não fechado
    return _res('incompleto', 'arquivo sem rodapé (crash não-recuperado)',
                leituras=validas, total=len(validas))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest ingestao/tests/test_validador.py -q`
Expected: PASS. (Testes antigos que montavam arquivos v1 na mão precisam ser regerados via `ArquivoDiario` v2, como no helper `_preparar`.)

- [ ] **Step 5: Commit**

```bash
git add ingestao/validador.py ingestao/tests/test_validador.py
git commit -m "feat(validador): v2 unificado sobre contrato.formato — hdr_sig, sig/linha, incompleto"
```

---

### Task 6: `file.ledger` incompleto + ingestor tenant-check + Timescale tags (cliente/pubkey/hash/ts_ingestao)

**Files:**
- Modify: `addons/afr_sentinela_sensor_monitor/models/file_ledger.py` (valor `incompleto` no Selection)
- Modify: `timescale/init.sql` (colunas de proveniência)
- Modify: `ingestao/timescale.py` (`inserir_leituras` grava as tags)
- Modify: `ingestao/ingestor.py` (cross-check tenant; passa proveniência)
- Modify: `ingestao/odoo_cliente.py` (`resolver_coletor` devolve `cliente_id`)
- Test: `ingestao/tests/test_ingestor.py`, `ingestao/tests/test_timescale.py`, `addons/.../tests/test_file_ledger.py`

**Interfaces:**
- Consumes: `ResultadoValidacao` (Task 5) com `cliente_id`/`site_id`/`incompleto`.
- Produces: `sensor_reading` com `cliente_id`, `pubkey_fingerprint`, `file_hash`, `ts_ingestao`; ledger aceita `incompleto`; ingestão rejeita arquivo cujo tenant do header diverge do cadastro.

- [ ] **Step 1: Write the failing tests**

(a) `file.ledger` — teste Odoo em `addons/.../tests/test_file_ledger.py`:

```python
    def test_status_incompleto_e_aceito(self):
        campos = self.env['sensor_monitor.file.ledger'].fields_get(['status_validacao'])
        valores = dict(campos['status_validacao']['selection'])
        assert 'incompleto' in valores
```

(b) `ingestor` tenant-check — em `ingestao/tests/test_ingestor.py` (siga o padrão de mock do `cliente_odoo` já usado no arquivo):

```python
def test_rejeita_quando_tenant_do_header_diverge_do_cadastro(monkeypatch, tmp_path):
    from ingestao import ingestor, validador
    res_val = validador.ResultadoValidacao(
        status_validacao='valido', motivo_rejeicao=None, total_linhas=1,
        coletor_id='COL-1', data_referencia='2026-07-16', tipo_arquivo='leituras',
        cliente_id='CLI-INTRUSO', site_id='SITE-1', leituras=[])
    monkeypatch.setattr(validador, 'validar_arquivo', lambda *a, **k: res_val)
    # cadastro diz que COL-1 é do CLI-1 / SITE-1
    monkeypatch.setattr(ingestor.odoo_cliente, 'resolver_coletor',
                        lambda c, cid: {'id': 1, 'site_code': 'SITE-1', 'cliente_id': 'CLI-1'})
    escritos = {}
    monkeypatch.setattr(ingestor.odoo_cliente, 'escrever_ledger',
                        lambda *a, **k: escritos.setdefault('args', a))
    r = ingestor.ingerir_arquivo('x', 'reg', 'dsn', object())
    assert r.status_validacao == 'invalido'
    assert 'tenant' in r.motivo_rejeicao.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest ingestao/tests/test_ingestor.py::test_rejeita_quando_tenant_do_header_diverge_do_cadastro -q`
Expected: FAIL — não há cross-check de tenant.
Run (Odoo): `docker compose exec -T odoo odoo -d sentinela --test-enable --test-tags /afr_sentinela_sensor_monitor -u afr_sentinela_sensor_monitor --db_host=db --db_user=odoo --db_password=odoo --stop-after-init 2>&1 | grep -iE 'FAIL|ERROR'`
Expected: FAIL — `incompleto` ausente do Selection.

- [ ] **Step 3: Write minimal implementation**

(a) `file_ledger.py` — adicionar valor ao Selection `status_validacao`:

```python
    status_validacao = fields.Selection([
        ('valido', 'Válido'),
        ('incompleto', 'Incompleto (sem rodapé)'),
        ('invalido', 'Inválido'),
        ('pendente', 'Pendente'),
        ('faltante', 'Faltante'),
    ], default='pendente', required=True)
```

(b) `timescale/init.sql` — adicionar colunas ao `CREATE TABLE sensor_reading` (após `status_leitura`):

```sql
    cliente_id      TEXT,
    pubkey_fingerprint TEXT,
    file_hash       TEXT,
    ts_ingestao     TIMESTAMPTZ
```

E rodar a migração idempotente no DB já existente:

```bash
docker compose exec -T timescaledb psql -U sentinela -d sentinela -c "
ALTER TABLE sensor_reading
  ADD COLUMN IF NOT EXISTS cliente_id TEXT,
  ADD COLUMN IF NOT EXISTS pubkey_fingerprint TEXT,
  ADD COLUMN IF NOT EXISTS file_hash TEXT,
  ADD COLUMN IF NOT EXISTS ts_ingestao TIMESTAMPTZ;"
```

(c) `ingestao/timescale.py` — `inserir_leituras` grava as tags de proveniência (novos parâmetros):

```python
def inserir_leituras(conn, site_id, coletor_id, leituras,
                     cliente_id=None, pubkey_fingerprint=None, file_hash=None, ts_ingestao=None):
    if not leituras:
        return 0
    valores = [
        (
            leitura['timestamp'], site_id, coletor_id, leitura['sensor_id'],
            leitura['area_id'], leitura['tipo_medida'], leitura['valor'], leitura['unidade'],
            leitura['protocolo_origem'], leitura['status_leitura'],
            cliente_id, pubkey_fingerprint, file_hash, ts_ingestao,
        )
        for leitura in leituras
    ]
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO sensor_reading
                (time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade,
                 protocolo_origem, status_leitura, cliente_id, pubkey_fingerprint, file_hash, ts_ingestao)
            VALUES %s
            """,
            valores,
        )
    conn.commit()
    return len(valores)
```

(d) `ingestao/odoo_cliente.py` — `resolver_coletor` também devolve `cliente_id`. Substituir o final da função (linhas 44-50) para resolver o partner e derivar `cliente_id` com a **mesma fórmula** do publisher:

```python
    sites = executar(cliente, 'sensor_monitor.site', 'read', [site_id],
                     fields=['site_code', 'partner_id'])
    partner_id = sites[0]['partner_id'][0]
    partner = executar(cliente, 'res.partner', 'read', [partner_id], fields=['ref'])[0]
    cliente_id = partner.get('ref') or f"CLI-{partner_id}"
    return {
        'id': coletor['id'],
        'hub_id': hub_id,
        'site_id': site_id,
        'site_code': sites[0]['site_code'],
        'cliente_id': cliente_id,
    }
```

(e) `ingestao/ingestor.py` — cross-check tenant + passar proveniência. Após `resolver_coletor` e antes de processar:

```python
    # F: o tenant do header tem que casar com o cadastro do coletor.
    if (resultado_validacao.site_id != info_coletor['site_code']
            or resultado_validacao.cliente_id != info_coletor['cliente_id']):
        return ResultadoIngestao(
            status_validacao='invalido',
            motivo_rejeicao=(f"tenant do header diverge do cadastro: header="
                             f"({resultado_validacao.cliente_id}/{resultado_validacao.site_id}) "
                             f"cadastro=({info_coletor['cliente_id']}/{info_coletor['site_code']})"),
            total_linhas=resultado_validacao.total_linhas, total_gravado=0)
```

E aceitar `incompleto` como gravável (linhas autênticas): trocar a guarda `if status_validacao == 'valido':` por `if status_validacao in ('valido', 'incompleto'):`. Em `_processar_leituras`, passar proveniência:

```python
def _processar_leituras(dsn, info_coletor, rv, pubkey_fp, ts_ingestao):
    conn = timescale.conectar(dsn)
    try:
        return timescale.inserir_leituras(
            conn, info_coletor['site_code'], rv.coletor_id, rv.leituras,
            cliente_id=rv.cliente_id, pubkey_fingerprint=pubkey_fp,
            file_hash=rv.hash_final, ts_ingestao=ts_ingestao)
    finally:
        conn.close()
```

E o call-site em `ingerir_arquivo` (ramo leituras) passa a proveniência:

```python
            total_gravado = _processar_leituras(
                dsn, info_coletor, resultado_validacao,
                resultado_validacao.pubkey_fingerprint, datetime.utcnow())
```

> `pubkey_fp` vem de `resultado_validacao.pubkey_fingerprint` (já exposto pela Task 5 — não editar a Task 5). `ts_ingestao` = `datetime.utcnow()` (no ingestor, adicionar `from datetime import datetime`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest ingestao/tests/test_ingestor.py ingestao/tests/test_timescale.py -q`
Run (Odoo): `docker compose exec -T odoo odoo -d sentinela --test-enable --test-tags /afr_sentinela_sensor_monitor -u afr_sentinela_sensor_monitor --db_host=db --db_user=odoo --db_password=odoo --stop-after-init 2>&1 | grep -iE 'FAIL|ERROR'`
Expected: PASS / sem FAIL.

- [ ] **Step 5: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor/models/file_ledger.py timescale/init.sql \
        ingestao/timescale.py ingestao/ingestor.py ingestao/odoo_cliente.py \
        ingestao/tests/test_ingestor.py addons/afr_sentinela_sensor_monitor/tests/test_file_ledger.py
git commit -m "feat(ingestao): status incompleto + cross-check tenant + tags de proveniencia no Timescale"
```

---

## Self-Review (B + F)

- **§4.1 (fechar a janela forjável):** cada linha assinada no instante da escrita (Task 4) + `incompleto` aceita cauda autêntica de crash (Task 5). ✔
- **§4.2 (header v2 + hdr_sig semeia cadeia):** Task 1 (formato) + Task 4 (escritor assina) + Task 5 (verifica). ✔
- **§4.3 (colunas cert_ver/cal_ganho/cal_offset + sig; hash inalterado):** Task 1 (formato), ordem exata; hash sobre `linha_sem_hash` (sem hash, sem sig). ✔
- **§4.4 (recalibração mid-dia sem marcador):** coeficientes por linha ⇒ a troca aparece na mudança de `cert_ver` entre linhas; nada especial a fazer no escritor. ✔
- **§4.5 (footer arquivo_sig):** `selar()` mantém `# assinatura:` = ECDSA sobre `hash_final`; popula `file.ledger.assinatura`. ✔
- **§3/F (tenant no header assinado + cross-check na ingestão):** Task 1 (header), Task 2 (publish), Task 5 (hdr_sig cobre cliente/site), Task 6 (cross-check + reject). ✔
- **§5.1 (ingestão: hdr_sig, sig por linha, incompleto, tags):** Tasks 5-6. ✔
- **§8 (alarme: header tenant + sig por linha):** header compartilhado (Task 1) + validador verifica sig para ambos os tipos (Task 5, loop único). ⚠ **Escopo:** o *escritor* de alarme do Hub não está ligado no `main.py` hoje (só leituras) — a capacidade de formato+verificação está pronta; o wiring do escritor de alarme fica para quando esse caminho existir. Documentado, não implementado aqui.
- **Format drift eliminado:** validador importa `contrato.formato.hash_seed`/`hash_linha` (não re-implementa). ✔
- **Custo de assinatura (§4.1/§7.3):** produção ≥1/min ⇒ ≤1440 sigs/dia; validar vazão do secure element no bring-up (prudência, fora deste plano de software). ✔
- **Nota operacional (fix wave review final, I3):** o cross-check de tenant (Task 6) compara o `cliente_id` do header — congelado no momento da publicação (Task 2) — com o cadastro atual do coletor no Odoo (`resolver_coletor` → `partner.ref`). Trocar o `ref` do partner de um cliente **depois** de arquivos já publicados invalida em cadeia todos os arquivos em trânsito desse tenant (rejeitados como `invalido`/tenant mismatch na ingestão). É fail-closed por desenho — não é um bug. Operadores devem republicar os arquivos afetados ou evitar alterar `ref` de tenants com coletores ativos em campo.
- Tipos consistentes: `cert_ver:int`, `cal_ganho/cal_offset:float`, `calibracao` dict com chaves `cert_ver/ganho/offset` — mesma forma em config_publisher (E), CanalConfig (Task 2), leitura dict (Task 3), coluna (Task 1). ✔
