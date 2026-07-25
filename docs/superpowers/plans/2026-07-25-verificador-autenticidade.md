# Verificador de autenticidade — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Núcleo de verificação de autenticidade desacoplado da fonte dos bytes, mais um CLI que o consome — base para o futuro endpoint HTTP/página web.

**Architecture:** Núcleo `ingestao/verificador.py` recebe `Iterable[(nome, bytes)]` e devolve `VerificacaoLote` estruturado. Reusa a cripto existente via `validador.validar_texto` (extraído nesta entrega) e resolve a chave por registro (modo A) ou PEM+fingerprint (modo B). CLI `scripts/verificar_autenticidade.py` alimenta o núcleo a partir de arquivo/diretório no disco.

**Tech Stack:** Python 3.9, `cryptography` (ECDSA/EC), `argparse`, `dataclasses`, `pytest`.

## Global Constraints

- Testes rodam da raiz do repo com `PYTHONPATH=. python -m pytest <alvo> -q`.
- Não há `.venv` nesta base — usar o `python` do sistema.
- Python 3.9: usar `Optional[X]`/`Union` OU `X | None` (a base já usa ambos; seguir o arquivo que está editando). Dataclasses com `field(default_factory=...)` para coleções.
- Assinatura ECDSA: `ec.ECDSA(hashes.SHA256())`; sig gravada em base64; hash conferido sobre `hash_hex.encode()`.
- Estados de item (strings exatas): `valido`, `invalido`, `incompleto`, `indeterminado`.
- Mensagens de erro/motivo em português (segue o código existente).
- Commits: assunto conciso; terminar corpo com `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## File Structure

- **Create** `ingestao/verificador.py` — núcleo: dataclasses `VerificacaoItem`/`VerificacaoLote` + `verificar_itens(...)`.
- **Create** `scripts/verificar_autenticidade.py` — adaptador CLI (walk disco → núcleo → saída humana/JSON + exit codes).
- **Create** `ingestao/tests/test_verificador.py` — testes do núcleo.
- **Create** `scripts/tests/test_verificar_autenticidade.py` — testes do CLI (novo dir + `__init__.py` se necessário).
- **Modify** `contrato/identidade.py` — adiciona `fingerprint_de_publica(chave_publica)`; `fingerprint_publica` delega.
- **Modify** `ingestao/validador.py` — extrai `validar_texto(texto, chave_publica)`; `validar_arquivo` vira wrapper.

---

## Task 1: `identidade.fingerprint_de_publica`

**Files:**
- Modify: `contrato/identidade.py:22-29` (função `fingerprint_publica`)
- Test: `ingestao/tests/test_verificador.py` (arquivo novo — só este teste por ora)

**Interfaces:**
- Produces: `fingerprint_de_publica(chave_publica) -> str` — fingerprint no mesmo formato de `fingerprint_publica` (SHA256 do DER SubjectPublicKeyInfo, hex uppercase, pares separados por `:`).

- [ ] **Step 1: Write the failing test**

Criar `ingestao/tests/test_verificador.py` com:

```python
from cryptography.hazmat.primitives.asymmetric import ec

from contrato import identidade


def test_fingerprint_de_publica_bate_com_fingerprint_privada():
    chave = ec.generate_private_key(ec.SECP256R1())
    assert identidade.fingerprint_de_publica(chave.public_key()) == identidade.fingerprint_publica(chave)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest ingestao/tests/test_verificador.py -q`
Expected: FAIL — `AttributeError: module 'contrato.identidade' has no attribute 'fingerprint_de_publica'`

- [ ] **Step 3: Write minimal implementation**

Em `contrato/identidade.py`, substituir a função `fingerprint_publica` atual por:

```python
def fingerprint_de_publica(chave_publica):
    chave_publica_der = chave_publica.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    digest = hashlib.sha256(chave_publica_der).hexdigest().upper()
    return ':'.join(digest[i:i + 2] for i in range(0, len(digest), 2))


def fingerprint_publica(chave_privada):
    return fingerprint_de_publica(chave_privada.public_key())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest ingestao/tests/test_verificador.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Run regressão dos consumidores do fingerprint**

Run: `PYTHONPATH=. python -m pytest hub/tests/test_assinador.py ingestao/tests/test_validador.py ingestao/tests/test_registro_coletores.py -q`
Expected: PASS (tudo verde — `assinador.fingerprint()` usa `fingerprint_publica`, comportamento inalterado)

- [ ] **Step 6: Commit**

```bash
git add contrato/identidade.py ingestao/tests/test_verificador.py
git commit -m "feat(identidade): fingerprint_de_publica para chave publica avulsa

Necessario no modo auditor (PEM avulso): conferir a chave fornecida contra
o coletor_pubkey_fingerprint do header. fingerprint_publica passa a delegar.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Extrair `validar_texto` de `validar_arquivo`

**Files:**
- Modify: `ingestao/validador.py:114-190` (função `validar_arquivo`)
- Test: `ingestao/tests/test_validador.py` (adiciona 1 teste do novo entrypoint)

**Interfaces:**
- Consumes: `parse_arquivo`, `parse_linha_leitura`, `parse_linha_alarme`, `_verificar_sig`, `formato.hash_seed`, `formato.hash_linha`, `ResultadoValidacao` (todos já em `validador.py`).
- Produces:
  - `validar_texto(texto: str, chave_publica) -> ResultadoValidacao` — todo o miolo de verificação (hdr_sig + cadeia + sig por linha + footer), recebendo a chave pública já resolvida.
  - `validar_arquivo(caminho, registro_path) -> ResultadoValidacao` — inalterado externamente: lê arquivo, resolve chave no registro (KeyError → `invalido`), delega a `validar_texto`.

- [ ] **Step 1: Write the failing test**

Adicionar a `ingestao/tests/test_validador.py`:

```python
def test_validar_texto_aceita_chave_publica_resolvida(tmp_path):
    caminho, registro = _preparar(tmp_path, selar=True)
    chave_publica = registro_coletores.obter_chave_publica(registro, 'COL-1')
    texto = caminho.read_text()
    r = validador.validar_texto(texto, chave_publica)
    assert r.status_validacao == 'valido'
    assert r.total_linhas == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest ingestao/tests/test_validador.py::test_validar_texto_aceita_chave_publica_resolvida -q`
Expected: FAIL — `AttributeError: module 'ingestao.validador' has no attribute 'validar_texto'`

- [ ] **Step 3: Refatorar `validador.py`**

Substituir a função `validar_arquivo` (linhas 114-190) por esta dupla. O corpo de `validar_texto` é o miolo atual, exceto: (a) recebe `texto` e `chave_publica` em vez de ler arquivo e resolver registro; (b) o bloco `try/obter_chave_publica/except KeyError` sai de `validar_texto` e vira responsabilidade do wrapper.

```python
def validar_texto(texto, chave_publica):
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
            pubkey_fingerprint=metadados_cab.get('coletor_pubkey_fingerprint'),
            timezone_offset=metadados_cab.get('timezone_offset'))
        if leituras is not None:
            if tipo_arquivo == 'alarmes':
                r.eventos = leituras
            else:
                r.leituras = leituras
        return r

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


def validar_arquivo(caminho, registro_path):
    texto = Path(caminho).read_text()
    metadados_cab, _, linhas_corpo, metadados_rod = parse_arquivo(texto)
    coletor_id = metadados_cab.get('coletor_id')
    try:
        chave_publica = registro_coletores.obter_chave_publica(registro_path, coletor_id)
    except KeyError as exc:
        # header incompleto/coletor ausente: reproduz o resultado 'invalido' legado
        return ResultadoValidacao(
            status_validacao='invalido', motivo_rejeicao=str(exc),
            total_linhas=len(linhas_corpo),
            coletor_id=coletor_id, data_referencia=metadados_cab.get('data_referencia'),
            hash_final=metadados_rod.get('hash_final'), assinatura=metadados_rod.get('assinatura'),
            tipo_arquivo=metadados_cab.get('tipo_arquivo'), cliente_id=metadados_cab.get('cliente_id'),
            site_id=metadados_cab.get('site_id'),
            pubkey_fingerprint=metadados_cab.get('coletor_pubkey_fingerprint'),
            timezone_offset=metadados_cab.get('timezone_offset'))
    return validar_texto(texto, chave_publica)
```

- [ ] **Step 4: Run new + regression**

Run: `PYTHONPATH=. python -m pytest ingestao/tests/test_validador.py ingestao/tests/test_confronto.py -q`
Expected: PASS (12 do validador + confronto verdes — `test_validar_arquivo_coletor_nao_registrado` continua `invalido` com "não registrado")

- [ ] **Step 5: Commit**

```bash
git add ingestao/validador.py ingestao/tests/test_validador.py
git commit -m "refactor(validador): extrai validar_texto de validar_arquivo

validar_texto recebe a chave publica ja resolvida (miolo hdr_sig+cadeia+
footer). validar_arquivo vira wrapper que resolve a chave no registro. Base
para o nucleo verificador consumir texto+chave sem tocar o filesystem.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Núcleo `verificar_itens` — modo A (registro)

**Files:**
- Create: `ingestao/verificador.py`
- Test: `ingestao/tests/test_verificador.py` (adiciona testes do núcleo)

**Interfaces:**
- Consumes: `validador.parse_arquivo`, `validador.validar_texto`, `registro_coletores.obter_chave_publica`.
- Produces:
  - `VerificacaoItem(nome, estado, motivo, coletor_id, data_referencia, total_linhas, hash_final, fingerprint_conferido)` — dataclass.
  - `VerificacaoLote(itens, total, validos, invalidos, incompletos, indeterminados, todos_ok)` — dataclass.
  - `verificar_itens(itens, *, registro_path=None, pem_bytes=None) -> VerificacaoLote` — nesta task só o caminho `registro_path` (modo A); `pem_bytes` fica na Task 4.
  - `_MAPA_ESTADO = {'valido': 'valido', 'invalido': 'invalido', 'incompleto': 'incompleto'}`.

- [ ] **Step 1: Write the failing tests**

Adicionar a `ingestao/tests/test_verificador.py` (topo do arquivo, imports + helper; reusa o padrão de `test_validador.py`):

```python
from datetime import datetime

from hub.arquivo_diario import ArquivoDiario
from hub.assinador import AssinadorSoftware
from ingestao import registro_coletores, verificador


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
    return arq.caminho('2026-07-16'), registro, assinador


def _bytes(caminho):
    return ('arquivo.txt', open(caminho, 'rb').read())


def test_modo_a_arquivo_valido(tmp_path):
    caminho, registro, _ = _preparar(tmp_path, selar=True)
    lote = verificador.verificar_itens([_bytes(caminho)], registro_path=registro)
    assert lote.total == 1 and lote.validos == 1 and lote.todos_ok is True
    item = lote.itens[0]
    assert item.estado == 'valido'
    assert item.coletor_id == 'COL-1'
    assert item.total_linhas == 2
    assert item.fingerprint_conferido is None  # modo A não confere fingerprint


def test_modo_a_linha_adulterada_e_invalido(tmp_path):
    caminho, registro, _ = _preparar(tmp_path, selar=True)
    linhas = caminho.read_text().split('\n')
    i = next(i for i, l in enumerate(linhas) if l and not l.startswith('#'))
    campos = linhas[i].split('|'); campos[5] = '999.99'; linhas[i] = '|'.join(campos)
    caminho.write_text('\n'.join(linhas))
    lote = verificador.verificar_itens([_bytes(caminho)], registro_path=registro)
    assert lote.invalidos == 1 and lote.todos_ok is False
    assert lote.itens[0].estado == 'invalido'


def test_modo_a_sem_footer_e_incompleto(tmp_path):
    caminho, registro, _ = _preparar(tmp_path, selar=False)
    lote = verificador.verificar_itens([_bytes(caminho)], registro_path=registro)
    assert lote.incompletos == 1 and lote.todos_ok is False
    assert lote.itens[0].estado == 'incompleto'


def test_modo_a_coletor_nao_registrado_e_indeterminado(tmp_path):
    caminho, _, _ = _preparar(tmp_path, selar=True)
    registro_vazio = str(tmp_path / "vazio.json")
    lote = verificador.verificar_itens([_bytes(caminho)], registro_path=registro_vazio)
    assert lote.indeterminados == 1 and lote.todos_ok is False
    item = lote.itens[0]
    assert item.estado == 'indeterminado'
    assert 'não registrado' in item.motivo


def test_nao_e_arquivo_assinado_e_indeterminado(tmp_path):
    caminho = tmp_path / "qualquer.txt"
    caminho.write_text("isto nao e um arquivo assinado\n")
    lote = verificador.verificar_itens([_bytes(caminho)], registro_path=str(tmp_path / "reg.json"))
    assert lote.indeterminados == 1
    assert lote.itens[0].estado == 'indeterminado'


def test_bytes_nao_decodificaveis_e_indeterminado(tmp_path):
    lote = verificador.verificar_itens([('bin.txt', b'\xff\xfe\x00\x01')], registro_path=str(tmp_path / "reg.json"))
    assert lote.indeterminados == 1
    assert lote.itens[0].estado == 'indeterminado'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. python -m pytest ingestao/tests/test_verificador.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingestao.verificador'` (o teste da Task 1 também importa, tudo bem)

- [ ] **Step 3: Criar `ingestao/verificador.py` (modo A)**

```python
"""Núcleo de verificação de autenticidade, desacoplado da fonte dos bytes.

Recebe uma coleção de (nome, bytes) e devolve um veredito estruturado. Não faz
walk no disco nem sabe o que é zip — isso é dos adaptadores (CLI hoje, endpoint
HTTP amanhã). Reusa a cripto de validador.validar_texto.
"""
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Tuple

from ingestao import registro_coletores, validador

_MAPA_ESTADO = {'valido': 'valido', 'invalido': 'invalido', 'incompleto': 'incompleto'}


@dataclass
class VerificacaoItem:
    nome: str
    estado: str  # valido | invalido | incompleto | indeterminado
    motivo: Optional[str] = None
    coletor_id: Optional[str] = None
    data_referencia: Optional[str] = None
    total_linhas: int = 0
    hash_final: Optional[str] = None
    fingerprint_conferido: Optional[bool] = None


@dataclass
class VerificacaoLote:
    itens: List[VerificacaoItem] = field(default_factory=list)
    total: int = 0
    validos: int = 0
    invalidos: int = 0
    incompletos: int = 0
    indeterminados: int = 0
    todos_ok: bool = True


def _indeterminado(nome, motivo, coletor_id=None):
    return VerificacaoItem(nome=nome, estado='indeterminado', motivo=motivo, coletor_id=coletor_id)


def _verificar_um(nome, dados, registro_path, chave_pem, fp_pem):
    try:
        texto = dados.decode('utf-8')
    except UnicodeDecodeError:
        return _indeterminado(nome, 'conteúdo não é texto UTF-8 (não é um arquivo de leitura)')

    metadados_cab = validador.parse_arquivo(texto)[0]
    coletor_id = metadados_cab.get('coletor_id')
    if not coletor_id or not metadados_cab.get('hdr_sig'):
        return _indeterminado(nome, 'não é um arquivo de leitura assinado (header ausente)')

    fingerprint_conferido = None
    if chave_pem is not None:  # modo B — preenchido na Task 4
        fp_header = metadados_cab.get('coletor_pubkey_fingerprint')
        if fp_pem != fp_header:
            return VerificacaoItem(
                nome=nome, estado='invalido', coletor_id=coletor_id,
                data_referencia=metadados_cab.get('data_referencia'),
                fingerprint_conferido=False,
                motivo='chave fornecida não corresponde ao fingerprint declarado no header')
        chave_publica = chave_pem
        fingerprint_conferido = True
    else:  # modo A — registro local
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


def verificar_itens(itens: Iterable[Tuple[str, bytes]], *, registro_path=None, pem_bytes=None) -> VerificacaoLote:
    chave_pem = None
    fp_pem = None
    # (modo B carregado na Task 4)

    lote = VerificacaoLote()
    for nome, dados in itens:
        item = _verificar_um(nome, dados, registro_path, chave_pem, fp_pem)
        lote.itens.append(item)
    lote.total = len(lote.itens)
    lote.validos = sum(1 for i in lote.itens if i.estado == 'valido')
    lote.invalidos = sum(1 for i in lote.itens if i.estado == 'invalido')
    lote.incompletos = sum(1 for i in lote.itens if i.estado == 'incompleto')
    lote.indeterminados = sum(1 for i in lote.itens if i.estado == 'indeterminado')
    lote.todos_ok = lote.invalidos == 0 and lote.indeterminados == 0
    return lote
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. python -m pytest ingestao/tests/test_verificador.py -q`
Expected: PASS (Task 1 + 6 testes de modo A verdes)

- [ ] **Step 5: Commit**

```bash
git add ingestao/verificador.py ingestao/tests/test_verificador.py
git commit -m "feat(verificador): nucleo verificar_itens modo registro (A)

Boundary (nome,bytes)->VerificacaoLote desacoplado do filesystem. Estados
valido/invalido/incompleto/indeterminado; coletor nao registrado e nao-arquivo
viram indeterminado (nao gritam adulteracao). Reusa validador.validar_texto.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Núcleo — modo B (PEM + conferência de fingerprint)

**Files:**
- Modify: `ingestao/verificador.py` (função `verificar_itens` — carregar `pem_bytes`)
- Test: `ingestao/tests/test_verificador.py` (adiciona testes de modo B)

**Interfaces:**
- Consumes: `contrato.identidade.fingerprint_de_publica` (Task 1); `cryptography.hazmat.primitives.serialization.load_pem_public_key`.
- Produces: `verificar_itens(..., pem_bytes=<bytes PEM>)` ativo. Levanta `ValueError` se `pem_bytes` for um PEM ilegível (o CLI trata → exit 4). O ramo `chave_pem is not None` já existe em `_verificar_um` desde a Task 3.

- [ ] **Step 1: Write the failing tests**

Adicionar a `ingestao/tests/test_verificador.py`:

```python
def test_modo_b_pem_correto_valido_com_fingerprint_conferido(tmp_path):
    caminho, _, assinador = _preparar(tmp_path, selar=True)
    pem = assinador.chave_publica_pem().encode()
    lote = verificador.verificar_itens([_bytes(caminho)], pem_bytes=pem)
    item = lote.itens[0]
    assert item.estado == 'valido'
    assert item.fingerprint_conferido is True
    assert lote.todos_ok is True


def test_modo_b_pem_de_outra_chave_e_invalido(tmp_path):
    caminho, _, _ = _preparar(tmp_path, selar=True)
    outro = AssinadorSoftware(str(tmp_path / "outra.pem"))
    lote = verificador.verificar_itens([_bytes(caminho)], pem_bytes=outro.chave_publica_pem().encode())
    item = lote.itens[0]
    assert item.estado == 'invalido'
    assert item.fingerprint_conferido is False
    assert 'fingerprint' in item.motivo


def test_modo_b_pem_ilegivel_levanta_valueerror(tmp_path):
    caminho, _, _ = _preparar(tmp_path, selar=True)
    import pytest
    with pytest.raises(ValueError):
        verificador.verificar_itens([_bytes(caminho)], pem_bytes=b'nao eh pem')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. python -m pytest ingestao/tests/test_verificador.py -k modo_b -q`
Expected: FAIL — `test_modo_b_pem_correto...` dá `invalido`/`fingerprint_conferido None` (pem ignorado); `test_modo_b_pem_ilegivel...` não levanta.

- [ ] **Step 3: Ativar modo B em `verificar_itens`**

Em `ingestao/verificador.py`, adicionar imports no topo:

```python
from cryptography.hazmat.primitives import serialization

from contrato import identidade
```

Substituir o bloco inicial de `verificar_itens` (as três linhas `chave_pem = None` / `fp_pem = None` / comentário) por:

```python
    chave_pem = None
    fp_pem = None
    if pem_bytes is not None:
        chave_pem = serialization.load_pem_public_key(pem_bytes)  # ValueError se ilegível
        fp_pem = identidade.fingerprint_de_publica(chave_pem)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. python -m pytest ingestao/tests/test_verificador.py -q`
Expected: PASS (todos: Task 1 + modo A + modo B)

- [ ] **Step 5: Commit**

```bash
git add ingestao/verificador.py ingestao/tests/test_verificador.py
git commit -m "feat(verificador): modo auditor (B) com PEM + conferencia de fingerprint

pem_bytes carrega a chave uma vez; confere contra coletor_pubkey_fingerprint
do header antes de validar. Mismatch = invalido (fingerprint_conferido False);
PEM ilegivel levanta ValueError p/ o CLI tratar.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Adaptador CLI `scripts/verificar_autenticidade.py`

**Files:**
- Create: `scripts/verificar_autenticidade.py`
- Create: `scripts/tests/__init__.py` (se `scripts/tests/` não existir)
- Test: `scripts/tests/test_verificar_autenticidade.py`

**Interfaces:**
- Consumes: `ingestao.verificador.verificar_itens`, `VerificacaoLote`.
- Produces:
  - `coletar_itens(caminho: str) -> list[tuple[str, bytes]]` — arquivo → 1 item `(nome, bytes)`; diretório → walk recursivo dos `*.txt` (nome = caminho relativo à raiz passada), ordenado. `FileNotFoundError` se o caminho não existe.
  - `codigo_saida(lote) -> int` — `1` se `invalidos>0`; senão `2` se `incompletos>0`; senão `3` se `indeterminados>0`; senão `0`.
  - `main(argv=None) -> int` — orquestra; retorna exit code (`4` em erro de uso).

- [ ] **Step 1: Write the failing tests**

Criar `scripts/tests/__init__.py` (vazio) e `scripts/tests/test_verificar_autenticidade.py`:

```python
import json
from datetime import datetime

from hub.arquivo_diario import ArquivoDiario
from hub.assinador import AssinadorSoftware
from ingestao import registro_coletores
from scripts import verificar_autenticidade as cli


def _leitura(ts):
    return {'timestamp': ts, 'sensor_id': 'SNR-1', 'area_id': 'EXPURGO',
            'tipo_medida': 'temperatura', 'valor': 96.83, 'unidade': 'C',
            'protocolo_origem': '4-20ma', 'status_leitura': 'ok',
            'cert_ver': 3, 'cal_ganho': 0.965, 'cal_offset': 0.33}


def _dia(tmp_path, subdir, coletor='COL-1', selar=True, registro=None):
    assinador = AssinadorSoftware(str(tmp_path / f"{subdir}.pem"))
    arq = ArquivoDiario(coletor, 'HUB-1', '2.3.1', '-03:00', str(tmp_path / subdir),
                        assinador, cliente_id='CLI-1', site_id='SITE-1')
    arq.registrar(_leitura(datetime(2026, 7, 16, 0, 1, 0)))
    if selar:
        arq.selar('2026-07-16')
    if registro:
        registro_coletores.registrar_coletor(registro, coletor, assinador.chave_publica_pem())
    return arq.caminho('2026-07-16')


def test_arquivo_unico_valido_exit_0(tmp_path, capsys):
    registro = str(tmp_path / "reg.json")
    caminho = _dia(tmp_path, "d", registro=registro)
    rc = cli.main([str(caminho), '--registro', registro])
    assert rc == 0
    assert 'valido' in capsys.readouterr().out.lower()


def test_diretorio_com_invalido_exit_1(tmp_path):
    registro = str(tmp_path / "reg.json")
    raiz = tmp_path / "arvore"
    bom = _dia(tmp_path, "arvore/ok", registro=registro)  # noqa: F841
    ruim = _dia(tmp_path, "arvore/ruim", registro=registro)
    linhas = ruim.read_text().split('\n')
    i = next(i for i, l in enumerate(linhas) if l and not l.startswith('#'))
    campos = linhas[i].split('|'); campos[5] = '1.23'; linhas[i] = '|'.join(campos)
    ruim.write_text('\n'.join(linhas))
    rc = cli.main([str(raiz), '--registro', registro])
    assert rc == 1


def test_json_output(tmp_path, capsys):
    registro = str(tmp_path / "reg.json")
    caminho = _dia(tmp_path, "d", registro=registro)
    rc = cli.main([str(caminho), '--registro', registro, '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['total'] == 1 and payload['validos'] == 1
    assert payload['itens'][0]['estado'] == 'valido'


def test_caminho_inexistente_exit_4(tmp_path):
    rc = cli.main([str(tmp_path / "nao-existe"), '--registro', str(tmp_path / "r.json")])
    assert rc == 4


def test_pem_ilegivel_exit_4(tmp_path):
    caminho = _dia(tmp_path, "d")
    pem = tmp_path / "ruim.pem"; pem.write_text("nao eh pem")
    rc = cli.main([str(caminho), '--pem', str(pem)])
    assert rc == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. python -m pytest scripts/tests/test_verificar_autenticidade.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.verificar_autenticidade'`

- [ ] **Step 3: Criar `scripts/verificar_autenticidade.py`**

```python
"""CLI de verificação de autenticidade de arquivos de leitura.

Adaptador fino sobre ingestao.verificador: lê arquivo/diretório do disco,
alimenta o núcleo (nome, bytes) e imprime veredito humano ou JSON. Exit codes:
0 todos válidos · 1 ≥1 inválido · 2 ≥1 incompleto · 3 ≥1 indeterminado ·
4 erro de uso. Precedência 4 > 1 > 3 > 2 > 0.
"""
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from ingestao import verificador


def coletar_itens(caminho):
    p = Path(caminho)
    if not p.exists():
        raise FileNotFoundError(f"caminho não encontrado: {caminho}")
    if p.is_file():
        return [(p.name, p.read_bytes())]
    itens = []
    for arq in sorted(p.rglob('*.txt')):
        if arq.is_file():
            itens.append((str(arq.relative_to(p)), arq.read_bytes()))
    return itens


def codigo_saida(lote):
    if lote.invalidos > 0:
        return 1
    if lote.incompletos > 0:
        return 2
    if lote.indeterminados > 0:
        return 3
    return 0


_SIMBOLO = {'valido': 'OK ', 'invalido': 'X  ', 'incompleto': '~  ', 'indeterminado': '?  '}


def _imprimir_humano(lote):
    for i in lote.itens:
        base = f"{_SIMBOLO.get(i.estado, '?  ')} {i.estado.upper():13} {i.nome}"
        detalhe = f"  coletor={i.coletor_id or '-'} data={i.data_referencia or '-'} linhas={i.total_linhas}"
        if i.fingerprint_conferido is not None:
            detalhe += f" fingerprint={'OK' if i.fingerprint_conferido else 'FALHOU'}"
        print(base + detalhe)
        if i.motivo:
            print(f"       motivo: {i.motivo}")
    print(f"\nresumo: {lote.total} arquivo(s) — "
          f"{lote.validos} valido(s), {lote.invalidos} invalido(s), "
          f"{lote.incompletos} incompleto(s), {lote.indeterminados} indeterminado(s)")


def main(argv=None):
    parser = argparse.ArgumentParser(description='Verifica autenticidade de arquivos de leitura assinados')
    parser.add_argument('caminho', help='arquivo .txt assinado ou diretório (walk recursivo)')
    parser.add_argument('--registro', default='ingestao/coletores_conhecidos.json',
                        help='registro de coletores (modo interno)')
    parser.add_argument('--pem', help='chave pública PEM do coletor (modo auditor)')
    parser.add_argument('--json', action='store_true', dest='saida_json', help='saída JSON')
    args = parser.parse_args(argv)

    try:
        itens = coletar_itens(args.caminho)
    except OSError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 4

    pem_bytes = None
    if args.pem:
        try:
            pem_bytes = Path(args.pem).read_bytes()
        except OSError as exc:
            print(f"erro: PEM ilegível: {exc}", file=sys.stderr)
            return 4

    try:
        lote = verificador.verificar_itens(
            itens, registro_path=args.registro, pem_bytes=pem_bytes)
    except ValueError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 4

    if args.saida_json:
        print(json.dumps(asdict(lote), ensure_ascii=False, indent=2))
    else:
        _imprimir_humano(lote)
    return codigo_saida(lote)


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. python -m pytest scripts/tests/test_verificar_autenticidade.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Smoke test manual (CLI real)**

Run: `PYTHONPATH=. python scripts/verificar_autenticidade.py --help`
Expected: imprime o usage com `caminho`, `--registro`, `--pem`, `--json`.

- [ ] **Step 6: Commit**

```bash
git add scripts/verificar_autenticidade.py scripts/tests/__init__.py scripts/tests/test_verificar_autenticidade.py
git commit -m "feat(cli): verificar_autenticidade — arquivo/diretorio, JSON, exit codes

Adaptador fino sobre o nucleo: walk recursivo de .txt, saida humana ou --json,
exit 0/1/2/3/4 (precedencia 4>1>3>2>0). Consome verificar_itens sem duplicar
logica de veredito.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Verificação final da entrega

**Files:** nenhum (só execução de suíte)

- [ ] **Step 1: Rodar toda a suíte tocada**

Run: `PYTHONPATH=. python -m pytest ingestao/tests/test_verificador.py ingestao/tests/test_validador.py ingestao/tests/test_confronto.py ingestao/tests/test_registro_coletores.py hub/tests/test_assinador.py scripts/tests/test_verificar_autenticidade.py -q`
Expected: PASS (tudo verde — núcleo + CLI + regressão de validador/confronto/assinador)

- [ ] **Step 2: Smoke end-to-end com árvore real**

Gerar um dia assinado num tmp, verificar via CLI diretório, conferir exit 0. (Se preferir, usar o `coletor_simulado.gerador` como em `test_validador._gerar_dia_e_registrar`.)

- [ ] **Step 3: Confirmar que nada além do escopo mudou**

Run: `git status --short && git log --oneline origin/master..HEAD`
Expected: só os arquivos do plano; commits das Tasks 1-5.

---

## Self-Review

**Spec coverage:**
- Boundary `(nome,bytes)`→`VerificacaoLote` → Task 3.
- Trust model A (registro) → Task 3; B (PEM+fingerprint) → Task 4.
- Estados valido/invalido/incompleto/indeterminado → Task 3 (mapa + guards) e Task 4 (mismatch=invalido).
- Estruturas JSON-serializáveis → Task 3 (dataclasses) + Task 5 (`asdict`+`--json`).
- CLI arquivo/diretório, `--registro`/`--pem`/`--json`, exit codes → Task 5.
- Refactor `validar_texto` + `fingerprint_de_publica` → Tasks 2 e 1.
- Testes (núcleo/CLI/refactor) → Tasks 1-6.
- Não-escopo (zip/HTTP/página/single-file) → não implementado; boundary deixa plugável.

**Placeholder scan:** sem TBD/TODO; todo passo tem código/comando/saída esperada.

**Type consistency:** `verificar_itens(itens, *, registro_path, pem_bytes)`, `VerificacaoItem`/`VerificacaoLote` com os mesmos campos em Tasks 3-5; `fingerprint_de_publica` (Task 1) consumido em Task 4; `coletar_itens`/`codigo_saida`/`main` consistentes em Task 5. `_MAPA_ESTADO` cobre os 3 status de `validar_texto`; `indeterminado` nunca vem de `validar_texto` (só dos guards do verificador).
