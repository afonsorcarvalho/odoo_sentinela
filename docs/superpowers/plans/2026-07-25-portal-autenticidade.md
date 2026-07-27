# Portal de autenticidade — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Portal web público (Odoo) onde qualquer pessoa sobe um arquivo de leitura assinado ou um zip e recebe um relatório de autenticidade de todos os arquivos, com fila/backpressure no api e chaves resolvidas do Odoo.

**Architecture:** Split. Odoo `website` (público) faz upload + throttle de borda + proxy/polling + renderiza relatório e laudo PDF. api (FastAPI, single-worker) descompacta zip, resolve chaves do Odoo (cache), roda `ingestao.verificador.verificar_itens`, com fila async (concorrência N) + rate-limit por-IP + TTL de resultado. Odoo é a fonte única das chaves públicas (`sensor_monitor.coletor.pubkey_pem`).

**Tech Stack:** Python 3.9, FastAPI + asyncio, `cryptography`, `zipfile` (stdlib), Odoo 18 (`website`, QWeb, controllers), pytest + FastAPI TestClient + Odoo HttpCase/TransactionCase.

## Global Constraints

- Testes Python rodam da raiz do repo com `PYTHONPATH=. python -m pytest <alvo> -q` (sem `.venv`; python do sistema).
- Testes Odoo: `docker exec odoo_sentinela-odoo-1 odoo -d sentinela -u <modulo> --test-enable --test-tags /<modulo> --http-port=8169 --stop-after-init` seguido de `docker restart odoo_sentinela-odoo-1`.
- **api DEVE permanecer single-worker** (Dockerfile `uvicorn` sem `--workers`). Jobs, rate-limit e TTL são estado em memória e dependem disso.
- Estados de item (verbatim): `valido` · `invalido` · `incompleto` · `indeterminado`.
- Fingerprint = SHA256 do DER SubjectPublicKeyInfo da chave pública, hex UPPERCASE, pares separados por `:`.
- `coletor_id` do arquivo mapeia `sensor_monitor.coletor.coletor_code` no Odoo.
- Guards de zip: upload ≤ 25 MB; total descomprimido ≤ 200 MB; ≤ 500 arquivos; zip aninhado ignorado.
- TTL do resultado do job: 600 s. Concorrência default N=2; fila máx 50; cota por-IP 10 req / 60 s (ajustáveis por env).
- Odoo é público (`auth='public'`); tudo que renderiza dado de upload trata erro como página amigável, nunca 500.
- Commits: assunto conciso; corpo termina com `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## File Structure

**Stage 1 — fonte das chaves**
- Modify `ingestao/verificador.py` — `verificar_itens(..., chaves_pem=None)`.
- Modify `addons/afr_sentinela_sensor_monitor/models/coletor.py` — `pubkey_pem` + `pubkey_fingerprint` computed.
- Modify `addons/afr_sentinela_sensor_monitor/views/coletor_views.xml` — campo no form.
- Create `addons/afr_sentinela_sensor_monitor/data/backfill_pubkey_pem.py` (server-action data ou post_init hook) — backfill do JSON.
- Create `api/verificacao_chaves.py` — dict `{coletor_code: pem}` do Odoo, cache TTL.

**Stage 2 — api verify+zip (síncrono)**
- Create `api/verificacao.py` — `descompactar()` + `verificar_upload()` (sync).

**Stage 3 — api fila + rate-limit**
- Modify `api/verificacao.py` — job store + worker pool + TTL.
- Create `api/verificacao_router.py` — `POST /verificar`, `GET /verificar/{job_id}`, rate-limit por-IP, 429.
- Modify `api/main.py` — `include_router` + start/stop do worker.

**Stage 4 — Odoo público**
- Create addon `addons/afr_sentinela_portal_autenticidade/` (`__manifest__.py`, `__init__.py`, `controllers/`, `models/verificacao_client.py`, `views/portal_templates.xml`, `static/src/js/portal_polling.js`, `security`).

**Stage 5 — relatório + PDF + JSON**
- Create `report/laudo_report.xml` + `report/laudo_templates.xml` + `models/verificacao_laudo.py` (TransientModel) no addon do portal; rotas de download no controller.

---

## Stage 1 — Fonte das chaves (fix durável)

### Task 1: Core `verificar_itens` aceita `chaves_pem` (registro em memória)

**Files:**
- Modify: `ingestao/verificador.py`
- Test: `ingestao/tests/test_verificador.py`

**Interfaces:**
- Consumes: `serialization.load_pem_public_key`, `validador.validar_texto` (existentes).
- Produces: `verificar_itens(itens, *, registro_path=None, pem_bytes=None, chaves_pem=None)`. `chaves_pem` é `dict[str, str]` (`coletor_code -> PEM`). Modo A resolve por esse dict quando fornecido; coletor ausente/PEM inválido → `indeterminado`. `registro_path` continua funcionando (retrocompat).

- [ ] **Step 1: Write the failing tests**

Adicionar a `ingestao/tests/test_verificador.py` (usa os helpers `_preparar`/`_bytes` já no arquivo):

```python
def test_modo_a_chaves_pem_dict_valido(tmp_path):
    caminho, _, assinador = _preparar(tmp_path, selar=True)
    chaves = {'COL-1': assinador.chave_publica_pem()}
    lote = verificador.verificar_itens([_bytes(caminho)], chaves_pem=chaves)
    assert lote.validos == 1 and lote.todos_ok is True
    assert lote.itens[0].estado == 'valido'
    assert lote.itens[0].fingerprint_conferido is None  # modo A


def test_modo_a_chaves_pem_coletor_ausente_indeterminado(tmp_path):
    caminho, _, _ = _preparar(tmp_path, selar=True)
    lote = verificador.verificar_itens([_bytes(caminho)], chaves_pem={'OUTRO': 'x'})
    assert lote.indeterminados == 1
    assert lote.itens[0].estado == 'indeterminado'
    assert 'não registrado' in lote.itens[0].motivo


def test_modo_a_chaves_pem_invalido_indeterminado(tmp_path):
    caminho, _, _ = _preparar(tmp_path, selar=True)
    lote = verificador.verificar_itens([_bytes(caminho)], chaves_pem={'COL-1': 'nao eh pem'})
    assert lote.indeterminados == 1
    assert lote.itens[0].estado == 'indeterminado'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. python -m pytest ingestao/tests/test_verificador.py -k chaves_pem -q`
Expected: FAIL — `verificar_itens() got an unexpected keyword argument 'chaves_pem'`

- [ ] **Step 3: Implement**

Em `ingestao/verificador.py`, trocar a assinatura de `_verificar_um` para receber um dict opcional de chaves públicas já carregadas, e ajustar o modo A:

```python
def _verificar_um(nome, dados, registro_path, chave_pem, fp_pem, chaves_pub):
    try:
        texto = dados.decode('utf-8')
    except UnicodeDecodeError:
        return _indeterminado(nome, 'conteúdo não é texto UTF-8 (não é um arquivo de leitura)')

    metadados_cab = validador.parse_arquivo(texto)[0]
    coletor_id = metadados_cab.get('coletor_id')
    if not coletor_id or not metadados_cab.get('hdr_sig'):
        return _indeterminado(nome, 'não é um arquivo de leitura assinado (header ausente)')

    fingerprint_conferido = None
    if chave_pem is not None:  # modo B
        fp_header = metadados_cab.get('coletor_pubkey_fingerprint')
        if not fp_header:
            return _indeterminado(
                nome, 'header sem coletor_pubkey_fingerprint (não confrontável com a chave fornecida)',
                coletor_id=coletor_id)
        if fp_pem != fp_header:
            return VerificacaoItem(
                nome=nome, estado='invalido', coletor_id=coletor_id,
                data_referencia=metadados_cab.get('data_referencia'),
                fingerprint_conferido=False,
                motivo='chave fornecida não corresponde ao fingerprint declarado no header')
        chave_publica = chave_pem
        fingerprint_conferido = True
    elif chaves_pub is not None:  # modo A — registro em memória (dict do Odoo)
        chave_publica = chaves_pub.get(coletor_id)
        if chave_publica is None:
            return _indeterminado(nome, f"coletor '{coletor_id}' não registrado", coletor_id=coletor_id)
    else:  # modo A — registro em arquivo (retrocompat)
        try:
            chave_publica = registro_coletores.obter_chave_publica(registro_path, coletor_id)
        except KeyError as exc:
            return _indeterminado(nome, str(exc), coletor_id=coletor_id)

    r = validador.validar_texto(texto, chave_publica)
    return VerificacaoItem(
        nome=nome, estado=_MAPA_ESTADO[r.status_validacao], motivo=r.motivo_rejeicao,
        coletor_id=r.coletor_id, data_referencia=r.data_referencia,
        total_linhas=r.total_linhas, hash_final=r.hash_final,
        fingerprint_conferido=fingerprint_conferido)
```

E em `verificar_itens`, pré-carregar o dict de chaves públicas (PEM inválido → coletor fica de fora, virando `indeterminado` na resolução):

```python
def verificar_itens(itens, *, registro_path=None, pem_bytes=None, chaves_pem=None):
    chave_pem = None
    fp_pem = None
    if pem_bytes is not None:
        chave_pem = serialization.load_pem_public_key(pem_bytes)
        fp_pem = identidade.fingerprint_de_publica(chave_pem)

    chaves_pub = None
    if chaves_pem is not None:
        chaves_pub = {}
        for cid, pem in chaves_pem.items():
            try:
                chaves_pub[cid] = serialization.load_pem_public_key(pem.encode())
            except (ValueError, TypeError):
                continue  # PEM inválido → coletor não resolvível → indeterminado

    lote = VerificacaoLote()
    for nome, dados in itens:
        lote.itens.append(_verificar_um(nome, dados, registro_path, chave_pem, fp_pem, chaves_pub))
    lote.total = len(lote.itens)
    lote.validos = sum(1 for i in lote.itens if i.estado == 'valido')
    lote.invalidos = sum(1 for i in lote.itens if i.estado == 'invalido')
    lote.incompletos = sum(1 for i in lote.itens if i.estado == 'incompleto')
    lote.indeterminados = sum(1 for i in lote.itens if i.estado == 'indeterminado')
    lote.todos_ok = (lote.total > 0 and lote.invalidos == 0
                     and lote.incompletos == 0 and lote.indeterminados == 0)
    return lote
```

- [ ] **Step 4: Run tests (new + regression)**

Run: `PYTHONPATH=. python -m pytest ingestao/tests/test_verificador.py scripts/tests/test_verificar_autenticidade.py -q`
Expected: PASS (novos 3 + todos os existentes — assinatura antiga preservada)

- [ ] **Step 5: Commit**

```bash
git add ingestao/verificador.py ingestao/tests/test_verificador.py
git commit -m "feat(verificador): registro em memoria via chaves_pem (dict coletor->PEM)

Modo A resolve a chave num dict {coletor_id:PEM} passado pelo chamador (fonte
Odoo), alternativa ao registro_path em arquivo. PEM invalido/coletor ausente ->
indeterminado. Retrocompat de registro_path preservada.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Odoo — `pubkey_pem` + `pubkey_fingerprint` computed no coletor

**Files:**
- Modify: `addons/afr_sentinela_sensor_monitor/models/coletor.py`
- Modify: `addons/afr_sentinela_sensor_monitor/views/coletor_views.xml`
- Test: `addons/afr_sentinela_sensor_monitor/tests/test_coletor_pubkey.py` (novo)

**Interfaces:**
- Produces: `sensor_monitor.coletor.pubkey_pem` (Text). `pubkey_fingerprint` vira `compute='_compute_pubkey_fingerprint'` `store=True` derivado do PEM (vazio se PEM ausente/inválido).

- [ ] **Step 1: Write the failing test**

Criar `addons/afr_sentinela_sensor_monitor/tests/test_coletor_pubkey.py`:

```python
from odoo.tests.common import TransactionCase


PEM_EXEMPLO = None  # preenchido no setUp a partir de uma chave gerada


class TestColetorPubkey(TransactionCase):
    def setUp(self):
        super().setUp()
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        chave = ec.generate_private_key(ec.SECP256R1())
        self.pem = chave.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        # fingerprint esperado (mesma formula do contrato.identidade)
        import hashlib
        der = chave.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        d = hashlib.sha256(der).hexdigest().upper()
        self.fp_esperado = ':'.join(d[i:i+2] for i in range(0, len(d), 2))
        self.hub = self.env['sensor_monitor.hub'].create({'name': 'H', 'hub_code': 'HUB-T'})

    def _coletor(self, pem):
        return self.env['sensor_monitor.coletor'].create({
            'name': 'C', 'coletor_code': 'COL-T', 'hub_id': self.hub.id,
            'tipo': 'esp32_wifi', 'pubkey_pem': pem,
        })

    def test_fingerprint_derivado_do_pem(self):
        col = self._coletor(self.pem)
        self.assertEqual(col.pubkey_fingerprint, self.fp_esperado)

    def test_pem_invalido_fingerprint_vazio(self):
        col = self._coletor('nao eh pem')
        self.assertFalse(col.pubkey_fingerprint)
```

> Nota: `hub_code`/campos do hub — se o `create` do hub exigir outros campos obrigatórios, ajustar conforme o modelo `sensor_monitor.hub` (checar antes de rodar).

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec odoo_sentinela-odoo-1 odoo -d sentinela -u afr_sentinela_sensor_monitor --test-enable --test-tags /afr_sentinela_sensor_monitor --http-port=8169 --stop-after-init 2>&1 | grep -iE "FAIL|ERROR|test_fingerprint|test_pem_invalido"`
Expected: FAIL — `pubkey_fingerprint` ainda é Char normal (não derivado), teste falha.

- [ ] **Step 3: Implement**

Em `addons/afr_sentinela_sensor_monitor/models/coletor.py`, adicionar o campo e o compute (trocar a linha `pubkey_fingerprint = fields.Char()`):

```python
import hashlib

from cryptography.hazmat.primitives import serialization
```

```python
    pubkey_pem = fields.Text(help='Chave pública (PEM) do coletor, usada na verificação de autenticidade.')
    pubkey_fingerprint = fields.Char(compute='_compute_pubkey_fingerprint', store=True)
```

```python
    @api.depends('pubkey_pem')
    def _compute_pubkey_fingerprint(self):
        for coletor in self:
            fp = False
            if coletor.pubkey_pem:
                try:
                    chave = serialization.load_pem_public_key(coletor.pubkey_pem.encode())
                    der = chave.public_bytes(
                        encoding=serialization.Encoding.DER,
                        format=serialization.PublicFormat.SubjectPublicKeyInfo,
                    )
                    d = hashlib.sha256(der).hexdigest().upper()
                    fp = ':'.join(d[i:i + 2] for i in range(0, len(d), 2))
                except (ValueError, TypeError):
                    fp = False
            coletor.pubkey_fingerprint = fp
```

Em `views/coletor_views.xml`, adicionar `pubkey_pem` ao form (perto de `pubkey_fingerprint`), campo de texto multi-linha; `pubkey_fingerprint` fica `readonly`.

- [ ] **Step 4: Run test + restart**

Run: `docker exec odoo_sentinela-odoo-1 odoo -d sentinela -u afr_sentinela_sensor_monitor --test-enable --test-tags /afr_sentinela_sensor_monitor --http-port=8169 --stop-after-init 2>&1 | tail -20 && docker restart odoo_sentinela-odoo-1`
Expected: os 2 testes novos PASS; suíte do módulo verde.

- [ ] **Step 5: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor/models/coletor.py addons/afr_sentinela_sensor_monitor/views/coletor_views.xml addons/afr_sentinela_sensor_monitor/tests/test_coletor_pubkey.py
git commit -m "feat(coletor): pubkey_pem + fingerprint computed do PEM

Odoo vira fonte da chave publica do coletor; fingerprint derivado (store)
com a mesma formula do contrato.identidade. Base p/ o portal resolver chaves.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Backfill do `coletores_conhecidos.json` para o Odoo

**Files:**
- Modify: `addons/afr_sentinela_sensor_monitor/__manifest__.py` (registrar `post_init_hook` se usado)
- Create: `addons/afr_sentinela_sensor_monitor/__init__.py` hook OU um script `scripts/backfill_pubkey_odoo.py`
- Test: `addons/afr_sentinela_sensor_monitor/tests/test_backfill_pubkey.py`

**Interfaces:**
- Produces: mecanismo idempotente que, dado o `coletores_conhecidos.json` (`{coletor_code: PEM}`), grava `pubkey_pem` nos coletores correspondentes já cadastrados no Odoo (casando por `coletor_code`). Coletor inexistente no Odoo é ignorado (log).

**Decisão de forma:** um **script standalone** `scripts/backfill_pubkey_odoo.py` (roda via api/odoo XML-RPC, fora do container odoo) é mais simples de testar e não acopla o import ao ciclo do addon. Usar o cliente `ingestao.odoo_cliente`.

- [ ] **Step 1: Write the failing test**

Criar `addons/afr_sentinela_sensor_monitor/tests/test_backfill_pubkey.py` como um teste puro do mapeamento (sem XML-RPC), extraindo a lógica de casamento numa função testável:

```python
import unittest

from scripts.backfill_pubkey_odoo import parear_registro


class TestBackfillPareamento(unittest.TestCase):
    def test_pareia_por_coletor_code(self):
        registro = {'COL-1': 'PEM1', 'COL-9': 'PEM9'}
        coletores_odoo = [{'id': 5, 'coletor_code': 'COL-1'}]
        pares = parear_registro(registro, coletores_odoo)
        self.assertEqual(pares, [(5, 'PEM1')])  # COL-9 sem coletor no Odoo -> ignorado
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest addons/afr_sentinela_sensor_monitor/tests/test_backfill_pubkey.py -q`
Expected: FAIL — `No module named 'scripts.backfill_pubkey_odoo'`

- [ ] **Step 3: Implement**

Criar `scripts/backfill_pubkey_odoo.py`:

```python
"""Backfill do coletores_conhecidos.json -> sensor_monitor.coletor.pubkey_pem.

Casa por coletor_code. Idempotente (write do mesmo PEM não muda nada).
Uso: PYTHONPATH=. python scripts/backfill_pubkey_odoo.py [--registro PATH]
"""
import argparse
import json
from pathlib import Path

from ingestao import odoo_cliente
from api.odoo import ODOO_URL, ODOO_DB, ODOO_USUARIO_SERVICO, ODOO_SENHA_SERVICO


def parear_registro(registro, coletores_odoo):
    por_code = {c['coletor_code']: c['id'] for c in coletores_odoo}
    return [(por_code[code], pem) for code, pem in registro.items() if code in por_code]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--registro', default='ingestao/coletores_conhecidos.json')
    args = parser.parse_args(argv)
    registro = json.loads(Path(args.registro).read_text())
    cliente = odoo_cliente.conectar(ODOO_URL, ODOO_DB, ODOO_USUARIO_SERVICO, ODOO_SENHA_SERVICO)
    coletores = odoo_cliente.executar(
        cliente, 'sensor_monitor.coletor', 'search_read', [], fields=['id', 'coletor_code'])
    pares = parear_registro(registro, coletores)
    for coletor_id, pem in pares:
        odoo_cliente.executar(cliente, 'sensor_monitor.coletor', 'write', [coletor_id], {'pubkey_pem': pem})
    print(f"backfill: {len(pares)} coletor(es) atualizado(s)")


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run test**

Run: `PYTHONPATH=. python -m pytest addons/afr_sentinela_sensor_monitor/tests/test_backfill_pubkey.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/backfill_pubkey_odoo.py addons/afr_sentinela_sensor_monitor/tests/test_backfill_pubkey.py
git commit -m "feat(backfill): coletores_conhecidos.json -> coletor.pubkey_pem

Script idempotente casa por coletor_code e grava o PEM no Odoo. Logica de
pareamento isolada e testada; XML-RPC via ingestao.odoo_cliente.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: api — resolver chaves do Odoo com cache (`api/verificacao_chaves.py`)

**Files:**
- Create: `api/verificacao_chaves.py`
- Test: `api/tests/test_verificacao_chaves.py`

**Interfaces:**
- Consumes: `api.odoo.get_cliente_servico`, `ingestao.odoo_cliente.executar`, `time.monotonic`.
- Produces: `chaves_do_odoo(force=False) -> dict[str, str]` (`coletor_code -> pem`), com cache de `_TTL_S` (60 s). `invalidar_cache()` para teste.

- [ ] **Step 1: Write the failing tests**

Criar `api/tests/test_verificacao_chaves.py`:

```python
from unittest import mock

from api import verificacao_chaves as vc


def test_chaves_do_odoo_monta_dict_e_cacheia(monkeypatch):
    vc.invalidar_cache()
    chamadas = {'n': 0}

    def fake_executar(cliente, model, method, *args, **kwargs):
        chamadas['n'] += 1
        return [
            {'coletor_code': 'COL-1', 'pubkey_pem': 'PEM1'},
            {'coletor_code': 'COL-2', 'pubkey_pem': 'PEM2'},
            {'coletor_code': 'COL-3', 'pubkey_pem': False},  # sem PEM -> fora
        ]

    monkeypatch.setattr(vc, 'get_cliente_servico', lambda: object())
    monkeypatch.setattr(vc.odoo_cliente, 'executar', fake_executar)

    d1 = vc.chaves_do_odoo()
    assert d1 == {'COL-1': 'PEM1', 'COL-2': 'PEM2'}
    d2 = vc.chaves_do_odoo()          # dentro do TTL -> cache
    assert d2 == d1
    assert chamadas['n'] == 1         # só uma ida ao Odoo

    d3 = vc.chaves_do_odoo(force=True)  # força refresh
    assert chamadas['n'] == 2
    assert d3 == d1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest api/tests/test_verificacao_chaves.py -q`
Expected: FAIL — `No module named 'api.verificacao_chaves'`

- [ ] **Step 3: Implement**

Criar `api/verificacao_chaves.py`:

```python
"""Resolve as chaves publicas dos coletores a partir do Odoo (fonte unica),
com cache de TTL curto. Usado pelo verificador do portal.
"""
import time

from ingestao import odoo_cliente

from .odoo import get_cliente_servico

_TTL_S = 60
_cache = {'em': None, 'dados': None}


def invalidar_cache():
    _cache['em'] = None
    _cache['dados'] = None


def chaves_do_odoo(force=False):
    agora = time.monotonic()
    if not force and _cache['dados'] is not None and (agora - _cache['em']) < _TTL_S:
        return _cache['dados']
    cliente = get_cliente_servico()
    linhas = odoo_cliente.executar(
        cliente, 'sensor_monitor.coletor', 'search_read', [],
        fields=['coletor_code', 'pubkey_pem'])
    dados = {l['coletor_code']: l['pubkey_pem'] for l in linhas if l.get('pubkey_pem')}
    _cache['dados'] = dados
    _cache['em'] = agora
    return dados
```

- [ ] **Step 4: Run test**

Run: `PYTHONPATH=. python -m pytest api/tests/test_verificacao_chaves.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add api/verificacao_chaves.py api/tests/test_verificacao_chaves.py
git commit -m "feat(api): resolve chaves publicas dos coletores do Odoo com cache

chaves_do_odoo() monta {coletor_code:PEM} via search_read, cache TTL 60s.
Fonte unica das chaves p/ o verificador do portal.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Stage 2 — api verify+zip (síncrono)

### Task 5: `api/verificacao.py` — descompactar zip com guards + `verificar_upload`

**Files:**
- Create: `api/verificacao.py`
- Test: `api/tests/test_verificacao_core.py`

**Interfaces:**
- Consumes: `zipfile`, `ingestao.verificador.verificar_itens`, `api.verificacao_chaves.chaves_do_odoo`.
- Produces:
  - Constantes: `UPLOAD_MAX = 25*1024*1024`, `DESCOMPRIMIDO_MAX = 200*1024*1024`, `ARQUIVOS_MAX = 500`.
  - `class LimiteExcedido(Exception)`.
  - `coletar(nome_upload: str, dados: bytes) -> list[tuple[str, bytes]]` — se `.zip`, descompacta (guards: total descomprimido, contagem; ignora diretórios e entradas aninhadas `.zip`); senão `[(nome_upload, dados)]`. `LimiteExcedido`/`zipfile.BadZipFile` em violação.
  - `verificar_upload(nome_upload, dados, chaves_pem=None) -> VerificacaoLote` — `coletar` + `verificar_itens(itens, chaves_pem=chaves_pem or chaves_do_odoo())`.

- [ ] **Step 1: Write the failing tests**

Criar `api/tests/test_verificacao_core.py`:

```python
import io
import zipfile

import pytest

from api import verificacao


def _zip(entradas):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for nome, dados in entradas:
            z.writestr(nome, dados)
    return buf.getvalue()


def test_coletar_arquivo_avulso():
    itens = verificacao.coletar('a.txt', b'conteudo')
    assert itens == [('a.txt', b'conteudo')]


def test_coletar_zip_lista_entradas():
    z = _zip([('x.txt', b'X'), ('sub/y.txt', b'Y')])
    itens = dict(verificacao.coletar('lote.zip', z))
    assert set(itens) == {'x.txt', 'sub/y.txt'}


def test_coletar_zip_ignora_aninhado_e_diretorio():
    z = _zip([('a.txt', b'A'), ('interno.zip', b'PK\x03\x04qualquer')])
    itens = dict(verificacao.coletar('lote.zip', z))
    assert 'a.txt' in itens and 'interno.zip' not in itens


def test_coletar_zip_estoura_contagem():
    z = _zip([(f'f{i}.txt', b'x') for i in range(verificacao.ARQUIVOS_MAX + 1)])
    with pytest.raises(verificacao.LimiteExcedido):
        verificacao.coletar('lote.zip', z)


def test_coletar_zip_estoura_descomprimido(monkeypatch):
    monkeypatch.setattr(verificacao, 'DESCOMPRIMIDO_MAX', 10)
    z = _zip([('big.txt', b'x' * 100)])
    with pytest.raises(verificacao.LimiteExcedido):
        verificacao.coletar('lote.zip', z)


def test_verificar_upload_usa_chaves(monkeypatch, tmp_path):
    # reusa fixture de arquivo assinado do verificador
    from ingestao.tests.test_verificador import _preparar
    caminho, _, assinador = _preparar(tmp_path, selar=True)
    dados = caminho.read_bytes()
    chaves = {'COL-1': assinador.chave_publica_pem()}
    lote = verificacao.verificar_upload('r.txt', dados, chaves_pem=chaves)
    assert lote.validos == 1 and lote.todos_ok is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. python -m pytest api/tests/test_verificacao_core.py -q`
Expected: FAIL — `No module named 'api.verificacao'`

- [ ] **Step 3: Implement**

Criar `api/verificacao.py`:

```python
"""Verificação de upload: descompacta zip (com guards) e roda o verificador.
Camada sync; a fila/worker vem no proximo stage.
"""
import io
import zipfile

from ingestao import verificador

from .verificacao_chaves import chaves_do_odoo

UPLOAD_MAX = 25 * 1024 * 1024
DESCOMPRIMIDO_MAX = 200 * 1024 * 1024
ARQUIVOS_MAX = 500


class LimiteExcedido(Exception):
    pass


def coletar(nome_upload, dados):
    if not nome_upload.lower().endswith('.zip'):
        return [(nome_upload, dados)]
    itens = []
    total = 0
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        infos = [i for i in z.infolist() if not i.is_dir()
                 and not i.filename.lower().endswith('.zip')]  # ignora aninhado
        if len(infos) > ARQUIVOS_MAX:
            raise LimiteExcedido(f'zip com mais de {ARQUIVOS_MAX} arquivos')
        for info in infos:
            total += info.file_size
            if total > DESCOMPRIMIDO_MAX:
                raise LimiteExcedido('conteúdo descomprimido excede o limite')
            itens.append((info.filename, z.read(info)))
    return itens


def verificar_upload(nome_upload, dados, chaves_pem=None):
    itens = coletar(nome_upload, dados)
    return verificador.verificar_itens(itens, chaves_pem=chaves_pem or chaves_do_odoo())
```

> Nota de segurança: `info.file_size` é o tamanho declarado no header do zip; a soma antes de extrair é o guard anti-bomba. `z.read` de cada entrada respeita esse teto porque paramos ao ultrapassar o total declarado.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=. python -m pytest api/tests/test_verificacao_core.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add api/verificacao.py api/tests/test_verificacao_core.py
git commit -m "feat(api): coletar zip com guards + verificar_upload

Descompacta zip (limites: contagem, total descomprimido; ignora aninhado/dir)
e roda verificar_itens com as chaves do Odoo. Camada sync.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Stage 3 — api fila + rate-limit + backpressure

### Task 6: Job store + worker pool + TTL

**Files:**
- Modify: `api/verificacao.py` (adiciona fila/jobs)
- Test: `api/tests/test_verificacao_fila.py`

**Interfaces:**
- Produces:
  - `dataclass Job(id, estado, posicao, criado_em, expira_em, lote=None, erro=None)`; estados `'fila'|'processando'|'pronto'|'erro'`.
  - `class FilaCheia(Exception)`.
  - `Gestor` (asyncio): `enfileirar(nome, dados) -> Job` (levanta `FilaCheia` se profundidade ≥ `FILA_MAX`); `obter(job_id) -> Job|None` (None se expirado/inexistente); `async start()`/`stop()`; worker roda `verificar_upload` com concorrência `CONCORRENCIA_N` via `asyncio.Semaphore`; sweep remove jobs com `expira_em` vencido.
  - Constantes: `FILA_MAX=50`, `CONCORRENCIA_N=2`, `TTL_RESULTADO_S=600`.
  - Injeção de tempo/relógio para teste: `Gestor(agora=callable)`.

- [ ] **Step 1: Write the failing tests**

Criar `api/tests/test_verificacao_fila.py` (usa `pytest.mark.asyncio` se disponível; senão `asyncio.run`). Testar: enfileira retorna job em `fila` com posição; processa até `pronto` com `lote`; `FilaCheia` quando cheia; job expira após TTL.

```python
import asyncio

from api import verificacao


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_enfileira_e_processa(monkeypatch):
    monkeypatch.setattr(verificacao, 'verificar_upload',
                        lambda nome, dados, chaves_pem=None: f'LOTE:{nome}')
    g = verificacao.Gestor()
    _run(g.start())
    try:
        job = g.enfileirar('a.txt', b'x')
        assert job.estado in ('fila', 'processando')
        _run(_espera_pronto(g, job.id))
        assert g.obter(job.id).estado == 'pronto'
        assert g.obter(job.id).lote == 'LOTE:a.txt'
    finally:
        _run(g.stop())


async def _espera_pronto(g, job_id, timeout=2.0):
    import time
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        if g.obter(job_id) and g.obter(job_id).estado in ('pronto', 'erro'):
            return
        await asyncio.sleep(0.02)
    raise AssertionError('job não ficou pronto')


def test_fila_cheia(monkeypatch):
    monkeypatch.setattr(verificacao, 'FILA_MAX', 0)
    g = verificacao.Gestor()
    import pytest
    with pytest.raises(verificacao.FilaCheia):
        g.enfileirar('a.txt', b'x')


def test_job_expira(monkeypatch):
    relogio = {'t': 1000.0}
    monkeypatch.setattr(verificacao, 'TTL_RESULTADO_S', 10)
    g = verificacao.Gestor(agora=lambda: relogio['t'])
    job = g.enfileirar('a.txt', b'x')
    job.estado = 'pronto'; job.lote = 'X'; job.expira_em = relogio['t'] + 10
    assert g.obter(job.id) is not None
    relogio['t'] += 11
    g.varrer_expirados()
    assert g.obter(job.id) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. python -m pytest api/tests/test_verificacao_fila.py -q`
Expected: FAIL — `Gestor`/`FilaCheia` inexistentes.

- [ ] **Step 3: Implement**

Adicionar a `api/verificacao.py` (topo: imports `asyncio`, `uuid`, `time`, `dataclass`):

```python
import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

FILA_MAX = 50
CONCORRENCIA_N = 2
TTL_RESULTADO_S = 600


class FilaCheia(Exception):
    pass


@dataclass
class Job:
    id: str
    estado: str = 'fila'
    posicao: int = 0
    criado_em: float = 0.0
    expira_em: Optional[float] = None
    lote: object = None
    erro: Optional[str] = None


class Gestor:
    def __init__(self, agora: Callable[[], float] = time.monotonic):
        self._agora = agora
        self._jobs = {}
        self._fila = asyncio.Queue()
        self._sem = asyncio.Semaphore(CONCORRENCIA_N)
        self._tarefas = []
        self._rodando = False

    def enfileirar(self, nome, dados):
        pendentes = sum(1 for j in self._jobs.values() if j.estado == 'fila')
        if pendentes >= FILA_MAX:
            raise FilaCheia('fila cheia')
        job = Job(id=uuid.uuid4().hex, criado_em=self._agora(), posicao=pendentes + 1)
        self._jobs[job.id] = job
        self._fila.put_nowait((job, nome, dados))
        return job

    def obter(self, job_id):
        return self._jobs.get(job_id)

    def varrer_expirados(self):
        agora = self._agora()
        for jid in [j.id for j in self._jobs.values()
                    if j.expira_em is not None and j.expira_em <= agora]:
            del self._jobs[jid]

    async def start(self):
        self._rodando = True
        self._tarefas = [asyncio.create_task(self._loop()) for _ in range(CONCORRENCIA_N)]

    async def stop(self):
        self._rodando = False
        for t in self._tarefas:
            t.cancel()
        self._tarefas = []

    async def _loop(self):
        while self._rodando:
            try:
                job, nome, dados = await asyncio.wait_for(self._fila.get(), timeout=0.2)
            except asyncio.TimeoutError:
                self.varrer_expirados()
                continue
            async with self._sem:
                job.estado = 'processando'
                try:
                    job.lote = await asyncio.to_thread(verificar_upload, nome, dados)
                    job.estado = 'pronto'
                except Exception as exc:  # LimiteExcedido, BadZipFile, etc.
                    job.estado = 'erro'
                    job.erro = str(exc)
                job.expira_em = self._agora() + TTL_RESULTADO_S
```

> Nota: `asyncio.to_thread` tira o trabalho CPU-bound (crypto) do event loop. O `Semaphore` limita concorrência real; a `Queue` segura o resto (backpressure).

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=. python -m pytest api/tests/test_verificacao_fila.py -q`
Expected: PASS. Se faltar `pytest-asyncio`, os testes usam `asyncio.run`/loop manual (já escritos assim) e passam sem plugin.

- [ ] **Step 5: Commit**

```bash
git add api/verificacao.py api/tests/test_verificacao_fila.py
git commit -m "feat(api): fila async de verificacao (pool N + TTL + backpressure)

Gestor com Queue + Semaphore(N); jobs fila->processando->pronto/erro; verificacao
CPU-bound via to_thread; FilaCheia quando cheia; sweep de TTL. Relogio injetavel.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Router `POST /verificar` + `GET /verificar/{job_id}` + rate-limit por-IP

**Files:**
- Create: `api/verificacao_router.py`
- Modify: `api/main.py` (include_router + start/stop do Gestor no lifespan)
- Test: `api/tests/test_verificacao_router.py`

**Interfaces:**
- Consumes: `verificacao.Gestor`, `verificacao.FilaCheia`, `verificacao.UPLOAD_MAX`.
- Produces:
  - `router` (APIRouter) com:
    - `POST /verificar` (multipart `arquivo: UploadFile`): lê bytes (rejeita > `UPLOAD_MAX` → 413); rate-limit por-IP (do header `X-Forwarded-For`, primeiro IP) → 429 + `Retry-After` se cota estourada; `enfileirar` → 200 `{job_id, posicao}`; `FilaCheia` → 429 + `Retry-After`.
    - `GET /verificar/{job_id}`: `obter`; None → 404; senão `{estado, posicao, lote?}` (`lote` só quando `pronto`, serializado com `dataclasses.asdict`).
  - `IP_COTA=10`, `IP_JANELA_S=60`; contador por-IP em memória com janela deslizante simples.
  - `gestor` (instância única do módulo), exposta p/ o lifespan do main.

- [ ] **Step 1: Write the failing tests**

Criar `api/tests/test_verificacao_router.py` (FastAPI TestClient; mocka `verificar_upload` p/ não depender do Odoo):

```python
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import verificacao, verificacao_router as vr


def _app(monkeypatch):
    monkeypatch.setattr(verificacao, 'verificar_upload',
                        lambda nome, dados, chaves_pem=None: verificacao.verificador.VerificacaoLote(total=0))
    vr.reset_estado()  # zera rate-limit + recria gestor
    app = FastAPI()
    app.include_router(vr.router)

    @app.on_event('startup')
    async def _s():
        await vr.gestor.start()

    @app.on_event('shutdown')
    async def _e():
        await vr.gestor.stop()
    return app


def test_post_retorna_job_id_e_get_evolui(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        r = c.post('/verificar', files={'arquivo': ('a.txt', b'x')},
                   headers={'X-Forwarded-For': '1.1.1.1'})
        assert r.status_code == 200
        jid = r.json()['job_id']
        # poll
        for _ in range(50):
            s = c.get(f'/verificar/{jid}').json()
            if s['estado'] in ('pronto', 'erro'):
                break
            time.sleep(0.02)
        assert s['estado'] == 'pronto'


def test_get_desconhecido_404(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        assert c.get('/verificar/naoexiste').status_code == 404


def test_rate_limit_por_ip_429(monkeypatch):
    monkeypatch.setattr(vr, 'IP_COTA', 2)
    with TestClient(_app(monkeypatch)) as c:
        h = {'X-Forwarded-For': '9.9.9.9'}
        assert c.post('/verificar', files={'arquivo': ('a.txt', b'x')}, headers=h).status_code == 200
        assert c.post('/verificar', files={'arquivo': ('a.txt', b'x')}, headers=h).status_code == 200
        r = c.post('/verificar', files={'arquivo': ('a.txt', b'x')}, headers=h)
        assert r.status_code == 429 and 'Retry-After' in r.headers
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. python -m pytest api/tests/test_verificacao_router.py -q`
Expected: FAIL — `No module named 'api.verificacao_router'`

- [ ] **Step 3: Implement**

Criar `api/verificacao_router.py`:

```python
import time
from collections import defaultdict, deque
from dataclasses import asdict

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from . import verificacao

IP_COTA = 10
IP_JANELA_S = 60

router = APIRouter()
gestor = verificacao.Gestor()
_hits = defaultdict(deque)  # ip -> timestamps


def reset_estado():
    global gestor
    gestor = verificacao.Gestor()
    _hits.clear()


def _ip(request: Request):
    xff = request.headers.get('x-forwarded-for', '')
    return xff.split(',')[0].strip() if xff else (request.client.host if request.client else 'desconhecido')


def _rate_ok(ip):
    agora = time.monotonic()
    dq = _hits[ip]
    while dq and agora - dq[0] > IP_JANELA_S:
        dq.popleft()
    if len(dq) >= IP_COTA:
        return False
    dq.append(agora)
    return True


@router.post('/verificar')
async def verificar(request: Request, arquivo: UploadFile = File(...)):
    if not _rate_ok(_ip(request)):
        return JSONResponse({'erro': 'muitas requisições'}, status_code=429,
                            headers={'Retry-After': str(IP_JANELA_S)})
    dados = await arquivo.read()
    if len(dados) > verificacao.UPLOAD_MAX:
        raise HTTPException(status_code=413, detail='upload excede o limite')
    try:
        job = gestor.enfileirar(arquivo.filename, dados)
    except verificacao.FilaCheia:
        return JSONResponse({'erro': 'servidor ocupado'}, status_code=429,
                            headers={'Retry-After': '30'})
    return {'job_id': job.id, 'posicao': job.posicao}


@router.get('/verificar/{job_id}')
async def status(job_id: str):
    job = gestor.obter(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail='job inexistente ou expirado')
    corpo = {'estado': job.estado, 'posicao': job.posicao}
    if job.estado == 'pronto':
        corpo['lote'] = asdict(job.lote)
    elif job.estado == 'erro':
        corpo['erro'] = job.erro
    return corpo
```

Em `api/main.py`: importar `verificacao_router`, `app.include_router(verificacao_router.router)`, e no startup/shutdown (ou lifespan) chamar `await verificacao_router.gestor.start()` / `stop()`. Seguir o padrão de start já usado por `live_listener` no main.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=. python -m pytest api/tests/test_verificacao_router.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Regressão do api**

Run: `PYTHONPATH=. python -m pytest api/tests -q`
Expected: PASS (suíte api verde; `main` importa o novo router sem quebrar).

- [ ] **Step 6: Commit**

```bash
git add api/verificacao_router.py api/main.py api/tests/test_verificacao_router.py
git commit -m "feat(api): rotas /verificar (fila) + rate-limit por-IP (XFF) + 429

POST enfileira (413 se upload grande, 429 se IP estoura cota ou fila cheia);
GET devolve status/lote. Gestor iniciado/parado no ciclo do app.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Stage 4 — Odoo público (novo addon)

### Task 8: Addon skeleton + cliente api + controller (página, POST proxy, status proxy)

**Files:**
- Create: `addons/afr_sentinela_portal_autenticidade/__init__.py`, `__manifest__.py`
- Create: `addons/afr_sentinela_portal_autenticidade/models/__init__.py`, `models/verificacao_client.py`
- Create: `addons/afr_sentinela_portal_autenticidade/controllers/__init__.py`, `controllers/portal.py`
- Create: `addons/afr_sentinela_portal_autenticidade/views/portal_templates.xml` (form + processando)
- Create: `addons/afr_sentinela_portal_autenticidade/static/src/js/portal_polling.js`
- Test: `addons/afr_sentinela_portal_autenticidade/tests/test_portal_controller.py`

**Interfaces:**
- Produces:
  - `verificacao_client.enviar(nome, dados, ip)` → `dict` (`{job_id, posicao}` ou levanta) e `status(job_id)` → `dict`. Base URL de `ir.config_parameter` `sentinela.api_base_url` (default `http://api:8000`).
  - Rotas: `GET /verificar-autenticidade` (form), `POST /verificar-autenticidade` (proxy → api), `GET /verificar-autenticidade/<job_id>` (JSON de status para o polling).

**Nota de teste (superfície mais difícil):** os testes usam `HttpCase` + `unittest.mock.patch` no `verificacao_client` (não bate no api real). Cada `Step` abaixo é pequeno, mas o conjunto é uma task só porque o controller não roda sem manifest+templates.

- [ ] **Step 1: Write the failing test**

Criar `addons/afr_sentinela_portal_autenticidade/tests/test_portal_controller.py`:

```python
from unittest.mock import patch

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestPortalController(HttpCase):
    def test_pagina_publica_200(self):
        r = self.url_open('/verificar-autenticidade')
        self.assertEqual(r.status_code, 200)
        self.assertIn('verifica', r.text.lower())

    def test_post_repassa_e_retorna_job(self):
        with patch(
            'odoo.addons.afr_sentinela_portal_autenticidade.models.verificacao_client'
            '.VerificacaoClient.enviar',
            return_value={'job_id': 'JID', 'posicao': 1},
        ):
            r = self.url_open('/verificar-autenticidade',
                              files={'arquivo': ('a.txt', b'x')})
            self.assertEqual(r.status_code, 200)
            self.assertIn('JID', r.text)

    def test_status_proxy(self):
        with patch(
            'odoo.addons.afr_sentinela_portal_autenticidade.models.verificacao_client'
            '.VerificacaoClient.status',
            return_value={'estado': 'processando', 'posicao': 2},
        ):
            r = self.url_open('/verificar-autenticidade/JID')
            self.assertEqual(r.status_code, 200)
            self.assertIn('processando', r.text)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec odoo_sentinela-odoo-1 odoo -d sentinela -i afr_sentinela_portal_autenticidade --test-enable --test-tags /afr_sentinela_portal_autenticidade --http-port=8169 --stop-after-init 2>&1 | tail -20`
Expected: FAIL — módulo inexistente (ou testes falham por falta de rotas).

- [ ] **Step 3: Implement — manifest e skeleton**

`__manifest__.py`:

```python
{
    'name': 'Sentinela — Portal de Autenticidade',
    'version': '18.0.1.0.0',
    'category': 'Website',
    'summary': 'Portal público para verificar a autenticidade de arquivos de leitura assinados',
    'depends': ['website', 'afr_sentinela_sensor_monitor'],
    'data': [
        'views/portal_templates.xml',
        'report/laudo_report.xml',        # criado no Stage 5 (deixar comentado até lá)
        'report/laudo_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'afr_sentinela_portal_autenticidade/static/src/js/portal_polling.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
```

> Deixar as duas linhas de `report/` comentadas até o Stage 5 criar os arquivos (senão o `-i` falha por data file ausente).

`__init__.py` → `from . import models, controllers`.
`models/__init__.py` → `from . import verificacao_client`.
`controllers/__init__.py` → `from . import portal`.

`models/verificacao_client.py`:

```python
import requests

from odoo import models


class VerificacaoClient(models.AbstractModel):
    _name = 'sensor_monitor.verificacao.client'
    _description = 'Cliente HTTP do serviço de verificação (api)'

    def _base_url(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'sentinela.api_base_url', 'http://api:8000')

    def enviar(self, nome, dados, ip):
        resp = requests.post(
            f'{self._base_url()}/verificar',
            files={'arquivo': (nome, dados)},
            headers={'X-Forwarded-For': ip or ''},
            timeout=30)
        resp.raise_for_status()
        return resp.json()

    def status(self, job_id):
        resp = requests.get(f'{self._base_url()}/verificar/{job_id}', timeout=15)
        if resp.status_code == 404:
            return {'estado': 'expirado'}
        resp.raise_for_status()
        return resp.json()
```

> `patch` no teste mira `VerificacaoClient.enviar/status` — manter esses nomes.

- [ ] **Step 4: Implement — controller**

`controllers/portal.py`:

```python
from odoo import http
from odoo.http import request


def _client():
    return request.env['sensor_monitor.verificacao.client'].sudo()


def _ip():
    xff = request.httprequest.headers.get('X-Forwarded-For', '')
    return xff.split(',')[0].strip() if xff else request.httprequest.remote_addr


class PortalAutenticidade(http.Controller):

    @http.route('/verificar-autenticidade', type='http', auth='public',
                website=True, methods=['GET'], csrf=False)
    def form(self, **kw):
        return request.render('afr_sentinela_portal_autenticidade.form', {})

    @http.route('/verificar-autenticidade', type='http', auth='public',
                website=True, methods=['POST'], csrf=False)
    def enviar(self, arquivo=None, **kw):
        if arquivo is None:
            return request.render('afr_sentinela_portal_autenticidade.form',
                                  {'erro': 'Selecione um arquivo.'})
        dados = arquivo.read()
        try:
            r = _client().enviar(arquivo.filename, dados, _ip())
        except Exception:
            return request.render('afr_sentinela_portal_autenticidade.form',
                                  {'erro': 'Servidor ocupado, tente novamente em instantes.'})
        return request.render('afr_sentinela_portal_autenticidade.processando',
                              {'job_id': r['job_id'], 'posicao': r.get('posicao', 0)})

    @http.route('/verificar-autenticidade/<job_id>', type='http', auth='public',
                website=True, methods=['GET'], csrf=False)
    def status(self, job_id, **kw):
        s = _client().status(job_id)
        # No Stage 5 este método passa a renderizar o relatório quando pronto.
        return request.make_json_response(s)
```

- [ ] **Step 5: Implement — templates (form + processando + JS)**

`views/portal_templates.xml` — dois templates QWeb website:
- `form`: `<form action="/verificar-autenticidade" method="post" enctype="multipart/form-data">` com `<input type="file" name="arquivo"/>`, botão, e exibição de `erro` se houver. Texto curto explicando (arquivo ou zip; veredito).
- `processando`: mostra "Processando… posição na fila: X", inclui um `<div id="job" data-job-id="{job_id}">` que o JS usa pra polling.

`static/src/js/portal_polling.js`: ao carregar a página `processando`, lê `data-job-id`, faz `fetch('/verificar-autenticidade/'+id)` a cada 2 s; enquanto `estado` ∈ {fila, processando} atualiza o texto; quando `pronto`/`erro`/`expirado`, recarrega a página (`window.location`) para o controller renderizar o relatório (Stage 5).

(Escrever o XML QWeb completo e o JS conforme convenção Odoo 18 website; manter os IDs `form`, `processando`, e o atributo `data-job-id`.)

- [ ] **Step 6: Run test + restart**

Run: `docker exec odoo_sentinela-odoo-1 odoo -d sentinela -i afr_sentinela_portal_autenticidade --test-enable --test-tags /afr_sentinela_portal_autenticidade --http-port=8169 --stop-after-init 2>&1 | tail -25 && docker restart odoo_sentinela-odoo-1`
Expected: os 3 testes do controller PASS.

- [ ] **Step 7: Commit**

```bash
git add addons/afr_sentinela_portal_autenticidade
git commit -m "feat(portal): addon publico + cliente api + controller upload/proxy/polling

Pagina publica /verificar-autenticidade (form), POST repassa bytes+IP ao api,
GET faz proxy do status. Cliente HTTP com base URL em ir.config_parameter.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Stage 5 — Relatório na tela + laudo PDF + JSON

### Task 9: Relatório + laudo PDF (QWeb) + download JSON

**Files:**
- Create: `addons/afr_sentinela_portal_autenticidade/report/laudo_report.xml`, `report/laudo_templates.xml`
- Create: `addons/afr_sentinela_portal_autenticidade/models/verificacao_laudo.py` (TransientModel)
- Modify: `controllers/portal.py` (relatório quando pronto + rotas `laudo.pdf` e `relatorio.json`)
- Modify: `__manifest__.py` (descomentar os data files de report; models/__init__)
- Modify: `views/portal_templates.xml` (template `relatorio`)
- Test: `addons/afr_sentinela_portal_autenticidade/tests/test_portal_relatorio.py`

**Interfaces:**
- Consumes: o `lote` (dict) devolvido pelo api quando `estado=='pronto'`.
- Produces:
  - `sensor_monitor.verificacao.laudo` (TransientModel) — campos que espelham `VerificacaoItem`/resumo; método `criar_de_lote(lote_dict) -> record` que popula um laudo + linhas (One2many transient). Efêmero (auto-vacuum).
  - Controller: `GET /verificar-autenticidade/<job_id>` renderiza `relatorio` (tela) quando pronto; `GET /verificar-autenticidade/<job_id>/laudo.pdf` → QWeb report PDF; `GET /verificar-autenticidade/<job_id>/relatorio.json` → o `lote` cru.

- [ ] **Step 1: Write the failing test**

Criar `addons/afr_sentinela_portal_autenticidade/tests/test_portal_relatorio.py`:

```python
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

LOTE = {
    'total': 2, 'validos': 1, 'invalidos': 1, 'incompletos': 0, 'indeterminados': 0,
    'todos_ok': False,
    'itens': [
        {'nome': 'a.txt', 'estado': 'valido', 'motivo': None, 'coletor_id': 'COL-1',
         'data_referencia': '2026-07-16', 'total_linhas': 2, 'hash_final': 'abc',
         'fingerprint_conferido': None},
        {'nome': 'b.txt', 'estado': 'invalido', 'motivo': 'cadeia quebrada',
         'coletor_id': 'COL-1', 'data_referencia': '2026-07-16', 'total_linhas': 0,
         'hash_final': None, 'fingerprint_conferido': None},
    ],
}


@tagged('post_install', '-at_install')
class TestPortalRelatorio(HttpCase):
    def _patch(self, estado='pronto'):
        return patch(
            'odoo.addons.afr_sentinela_portal_autenticidade.models.verificacao_client'
            '.VerificacaoClient.status',
            return_value={'estado': estado, 'lote': LOTE})

    def test_relatorio_na_tela(self):
        with self._patch():
            r = self.url_open('/verificar-autenticidade/JID')
            self.assertEqual(r.status_code, 200)
            self.assertIn('a.txt', r.text)
            self.assertIn('b.txt', r.text)

    def test_download_json(self):
        with self._patch():
            r = self.url_open('/verificar-autenticidade/JID/relatorio.json')
            self.assertEqual(r.status_code, 200)
            self.assertIn('application/json', r.headers.get('Content-Type', ''))
            self.assertIn('"total": 2', r.text)

    def test_laudo_pdf_nao_vazio(self):
        with self._patch():
            r = self.url_open('/verificar-autenticidade/JID/laudo.pdf')
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.content[:4] == b'%PDF')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec odoo_sentinela-odoo-1 odoo -d sentinela -u afr_sentinela_portal_autenticidade --test-enable --test-tags /afr_sentinela_portal_autenticidade --http-port=8169 --stop-after-init 2>&1 | tail -20`
Expected: FAIL — rotas/relatório/report inexistentes.

- [ ] **Step 3: Implement — TransientModel do laudo**

`models/verificacao_laudo.py`: `sensor_monitor.verificacao.laudo` (TransientModel) com campos de resumo (`total`, `validos`, `invalidos`, `incompletos`, `indeterminados`, `todos_ok`, `gerado_em`) e One2many `linha_ids` → `sensor_monitor.verificacao.laudo.linha` (TransientModel: `nome`, `estado`, `motivo`, `coletor_id`, `data_referencia`, `total_linhas`, `fingerprint_conferido`, `laudo_id`). Método `@api.model criar_de_lote(lote)` cria o laudo + linhas a partir do dict e devolve o record. Adicionar ambos a `models/__init__.py`.

- [ ] **Step 4: Implement — report QWeb + templates**

`report/laudo_report.xml`: um `ir.actions.report` (`report_type='qweb-pdf'`, `model='sensor_monitor.verificacao.laudo'`, `report_name='afr_sentinela_portal_autenticidade.laudo'`).
`report/laudo_templates.xml`: template QWeb do laudo (cabeçalho com timestamp, resumo, tabela por arquivo com estado colorido).
`views/portal_templates.xml`: adicionar template `relatorio` (website) — mesma informação na tela + botões "Baixar PDF" e "Baixar JSON".

- [ ] **Step 5: Implement — rotas de relatório/download**

Em `controllers/portal.py`, ajustar `status` e adicionar rotas:

```python
    @http.route('/verificar-autenticidade/<job_id>', type='http', auth='public',
                website=True, methods=['GET'], csrf=False)
    def status(self, job_id, **kw):
        s = _client().status(job_id)
        if s.get('estado') == 'pronto':
            laudo = request.env['sensor_monitor.verificacao.laudo'].sudo().criar_de_lote(s['lote'])
            return request.render('afr_sentinela_portal_autenticidade.relatorio',
                                  {'laudo': laudo, 'job_id': job_id})
        if request.httprequest.headers.get('Accept', '').startswith('application/json') or kw.get('json'):
            return request.make_json_response(s)
        # ainda processando: página com polling
        return request.render('afr_sentinela_portal_autenticidade.processando',
                              {'job_id': job_id, 'posicao': s.get('posicao', 0)})

    @http.route('/verificar-autenticidade/<job_id>/relatorio.json', type='http',
                auth='public', website=True, methods=['GET'], csrf=False)
    def download_json(self, job_id, **kw):
        s = _client().status(job_id)
        return request.make_json_response(s.get('lote', s))

    @http.route('/verificar-autenticidade/<job_id>/laudo.pdf', type='http',
                auth='public', website=True, methods=['GET'], csrf=False)
    def download_pdf(self, job_id, **kw):
        s = _client().status(job_id)
        if s.get('estado') != 'pronto':
            return request.not_found()
        laudo = request.env['sensor_monitor.verificacao.laudo'].sudo().criar_de_lote(s['lote'])
        pdf, _ = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'afr_sentinela_portal_autenticidade.laudo', res_ids=laudo.ids)
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', f'attachment; filename="laudo-{job_id}.pdf"')])
```

> O polling JS do Stage 4 recarrega a página `/verificar-autenticidade/<job_id>`; quando `pronto`, este `status` renderiza `relatorio`. O JS deve pedir JSON (header Accept) durante o polling e recarregar sem Accept ao terminar — ajustar o JS se necessário para essa distinção.

- [ ] **Step 6: Run test + restart**

Run: `docker exec odoo_sentinela-odoo-1 odoo -d sentinela -u afr_sentinela_portal_autenticidade --test-enable --test-tags /afr_sentinela_portal_autenticidade --http-port=8169 --stop-after-init 2>&1 | tail -25 && docker restart odoo_sentinela-odoo-1`
Expected: os 3 testes (tela, JSON, PDF) PASS.

- [ ] **Step 7: Commit**

```bash
git add addons/afr_sentinela_portal_autenticidade
git commit -m "feat(portal): relatorio na tela + laudo PDF (QWeb) + download JSON

TransientModel efemero espelha o lote; report qweb-pdf; controller renderiza
relatorio quando pronto e serve laudo.pdf/relatorio.json.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Verificação final da entrega

- [ ] **Step 1: Suíte Python (core + api)**

Run: `PYTHONPATH=. python -m pytest ingestao/tests/test_verificador.py api/tests -q`
Expected: PASS.

- [ ] **Step 2: Suíte Odoo (ambos os módulos)**

Run: `docker exec odoo_sentinela-odoo-1 odoo -d sentinela -u afr_sentinela_sensor_monitor,afr_sentinela_portal_autenticidade --test-enable --test-tags /afr_sentinela_sensor_monitor,/afr_sentinela_portal_autenticidade --http-port=8169 --stop-after-init 2>&1 | tail -30 && docker restart odoo_sentinela-odoo-1`
Expected: PASS.

- [ ] **Step 3: Smoke E2E manual** (com api de pé): subir um arquivo assinado real pela página `/verificar-autenticidade`, ver o relatório VÁLIDO, baixar PDF e JSON. Rodar `scripts/backfill_pubkey_odoo.py` antes, para o coletor real ter `pubkey_pem`.

- [ ] **Step 4: Confirmar escopo**

Run: `git status --short && git log --oneline origin/master..HEAD`
Expected: só arquivos do plano; commits das Tasks 1-9.

---

## Self-Review

**Spec coverage:**
- Fonte das chaves (Odoo) → Tasks 1-4. Core `chaves_pem` → 1; `pubkey_pem`+fingerprint → 2; backfill → 3; api resolve+cache → 4.
- api verify+zip+guards → 5. Fila/rate-limit/backpressure/TTL → 6-7.
- Odoo público/upload/proxy/polling → 8. Relatório tela+PDF+JSON → 9.
- Constraint single-worker → refletido em jobs/rate-limit em memória (6,7). Rate-limit por-IP via XFF → 7. TTL do resultado → 6 (sweep) + acessível em 9 dentro da janela.
- Testes por camada (core puro, api TestClient, Odoo HttpCase/TransactionCase) → em cada task; verificação final → 10.
- Não-escopo (modo B, histórico persistente, unificar ingestão, Redis) → não implementado.

**Placeholder scan:** As tasks 8 e 9 (QWeb/JS/templates website) descrevem os arquivos com precisão mas não trazem o XML/JS 100% verbatim — são a superfície Odoo-web, onde o formato exato depende de convenções da versão; o implementador escreve o QWeb seguindo as âncoras dadas (IDs de template, nomes de rota, campos do TransientModel, `data-job-id`). Todo código Python (core/api/models/controllers) está verbatim. Isto é intencional e sinalizado, não um placeholder de lógica.

**Type consistency:** `verificar_itens(..., chaves_pem)` (1) consumido por `verificar_upload` (5) via `chaves_do_odoo()` (4); `Gestor`/`Job`/`FilaCheia` (6) consumidos pelo router (7); `VerificacaoClient.enviar/status` (8) mockados nos testes 8/9 e usados pelo controller; `criar_de_lote(lote)` (9) consome o `lote` (asdict de `VerificacaoLote`) devolvido em 7. `coletor_code` = `coletor_id` do arquivo, usado em 3 (backfill) e 4 (dict).
