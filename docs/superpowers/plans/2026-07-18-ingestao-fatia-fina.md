# Serviço de Ingestão (fatia fina) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serviço Python standalone (`ingestao/`) que lê um arquivo de leituras gerado por `coletor_simulado/`, valida cadeia de hash + assinatura ECDSA, e grava as leituras válidas no TimescaleDB (`sensor_reading`, já existente da Fase 1).

**Architecture:** Três módulos (`registro_coletores.py` — chave pública por coletor, `validador.py` — parsing + verificação, `timescale.py` — gravação em lote) mais `ingestor.py` orquestrando os dois e expondo CLI. `validador.py` reimplementa a cadeia de hash independentemente de `coletor_simulado/formato.py` (nunca importado em código de produção — só em testes, como gerador de arquivo de teste).

**Tech Stack:** Python 3, `cryptography`, `psycopg2-binary`, `pytest`.

## Global Constraints

- Sem integração Odoo, sem processamento do arquivo de alarmes, sem SFTP/MQTT, sem proteção contra reingestão duplicada nesta rodada.
- `validador.py` e `registro_coletores.py` (fora de testes) **nunca importam `coletor_simulado`** — a fronteira arquitetural real (firmware C vs. servidor Python) é preservada mesmo o simulador sendo Python por conveniência.
- `site_id` fixo (`SITE-SIM-0001` no uso real via CLI; `SITE-TEST-*` nos testes) — sem Odoo pra resolver `coletor→hub→site` ainda.
- TimescaleDB já roda via `docker-compose.yml` da Fase 1 (`localhost:5433`, banco `sentinela`, usuário/senha `sentinela`) — Tasks 3–5 precisam desse container up (`docker compose up -d timescaledb` na raiz do repo).
- Formato de arquivo e cadeia de hash exatamente conforme `esp32_coletor_spec.md` §4 (idêntico ao que `coletor_simulado` já produz).

---

## Task 1: Registro de coletores conhecidos

**Files:**
- Create: `ingestao/__init__.py`
- Create: `ingestao/registro_coletores.py`
- Create: `ingestao/requirements.txt`
- Create: `ingestao/tests/__init__.py`
- Test: `ingestao/tests/test_registro_coletores.py`
- Modify: `.gitignore` (raiz do repo)

**Interfaces:**
- Produces: `carregar_registro(caminho) -> dict[str, str]`, `salvar_registro(caminho, registro) -> None`, `registrar_coletor(caminho, coletor_id, chave_publica_pem) -> None`, `obter_chave_publica(caminho, coletor_id) -> EllipticCurvePublicKey` (levanta `KeyError` se não registrado), `registrar_a_partir_de_chave_privada(caminho_registro, caminho_chave_privada, coletor_id) -> None` — todos em `ingestao/registro_coletores.py`, usados pelas Tasks 2 e 4.

- [ ] **Step 1: Criar `ingestao/requirements.txt`**

```
cryptography>=42
psycopg2-binary>=2.9
pytest>=8
```

- [ ] **Step 2: Criar `ingestao/__init__.py`** (vazio)

- [ ] **Step 3: Criar `ingestao/tests/__init__.py`** (vazio)

- [ ] **Step 4: Escrever o teste em `ingestao/tests/test_registro_coletores.py`**

```python
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from ingestao import registro_coletores


def _gerar_chave_privada_pem(tmp_path, nome='chave.pem'):
    chave = ec.generate_private_key(ec.SECP256R1())
    caminho = tmp_path / nome
    caminho.write_bytes(chave.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    return chave, caminho


def test_registrar_e_obter_chave_publica(tmp_path):
    chave, _ = _gerar_chave_privada_pem(tmp_path)
    chave_publica_pem = chave.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    registro_path = tmp_path / 'registro.json'
    registro_coletores.registrar_coletor(registro_path, 'COL-1', chave_publica_pem)
    chave_recuperada = registro_coletores.obter_chave_publica(registro_path, 'COL-1')
    assert chave_recuperada.public_numbers() == chave.public_key().public_numbers()


def test_obter_chave_publica_levanta_erro_para_coletor_nao_registrado(tmp_path):
    registro_path = tmp_path / 'registro.json'
    with pytest.raises(KeyError):
        registro_coletores.obter_chave_publica(registro_path, 'COL-INEXISTENTE')


def test_registrar_a_partir_de_chave_privada(tmp_path):
    chave, caminho_chave = _gerar_chave_privada_pem(tmp_path)
    registro_path = tmp_path / 'registro.json'
    registro_coletores.registrar_a_partir_de_chave_privada(registro_path, caminho_chave, 'COL-2')
    chave_recuperada = registro_coletores.obter_chave_publica(registro_path, 'COL-2')
    assert chave_recuperada.public_numbers() == chave.public_key().public_numbers()


def test_carregar_registro_vazio_quando_arquivo_nao_existe(tmp_path):
    registro_path = tmp_path / 'nao-existe.json'
    assert registro_coletores.carregar_registro(registro_path) == {}


def test_registrar_atualiza_entrada_existente(tmp_path):
    chave1, _ = _gerar_chave_privada_pem(tmp_path, 'chave1.pem')
    chave2, _ = _gerar_chave_privada_pem(tmp_path, 'chave2.pem')
    registro_path = tmp_path / 'registro.json'
    pem1 = chave1.public_key().public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    pem2 = chave2.public_key().public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    registro_coletores.registrar_coletor(registro_path, 'COL-3', pem1)
    registro_coletores.registrar_coletor(registro_path, 'COL-3', pem2)
    chave_recuperada = registro_coletores.obter_chave_publica(registro_path, 'COL-3')
    assert chave_recuperada.public_numbers() == chave2.public_key().public_numbers()
```

- [ ] **Step 5: Rodar os testes e confirmar que falham**

Run: `python3 -m pytest ingestao/tests/test_registro_coletores.py -v` (a partir da raiz do repo)
Expected: `ModuleNotFoundError: No module named 'ingestao.registro_coletores'`.

- [ ] **Step 6: Implementar `ingestao/registro_coletores.py`**

```python
import argparse
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization


def carregar_registro(caminho):
    caminho = Path(caminho)
    if not caminho.exists():
        return {}
    return json.loads(caminho.read_text())


def salvar_registro(caminho, registro):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(registro, indent=2))


def registrar_coletor(caminho, coletor_id, chave_publica_pem):
    registro = carregar_registro(caminho)
    registro[coletor_id] = chave_publica_pem
    salvar_registro(caminho, registro)


def obter_chave_publica(caminho, coletor_id):
    registro = carregar_registro(caminho)
    if coletor_id not in registro:
        raise KeyError(f"coletor '{coletor_id}' não registrado em {caminho}")
    return serialization.load_pem_public_key(registro[coletor_id].encode())


def registrar_a_partir_de_chave_privada(caminho_registro, caminho_chave_privada, coletor_id):
    chave_privada_bytes = Path(caminho_chave_privada).read_bytes()
    chave_privada = serialization.load_pem_private_key(chave_privada_bytes, password=None)
    chave_publica_pem = chave_privada.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    registrar_coletor(caminho_registro, coletor_id, chave_publica_pem)


def main():
    parser = argparse.ArgumentParser(description='Registro de coletores conhecidos')
    parser.add_argument('--registrar', required=True, help='coletor_id a registrar')
    parser.add_argument('--a-partir-de', required=True, dest='chave_privada', help='caminho da chave privada PEM')
    parser.add_argument('--registro', default='ingestao/coletores_conhecidos.json')
    args = parser.parse_args()
    registrar_a_partir_de_chave_privada(args.registro, args.chave_privada, args.registrar)
    print(f"Coletor {args.registrar} registrado em {args.registro}")


if __name__ == '__main__':
    main()
```

- [ ] **Step 7: Rodar os testes e confirmar que passam**

Run: `python3 -m pytest ingestao/tests/test_registro_coletores.py -v`
Expected: 5 passed.

- [ ] **Step 8: Atualizar `.gitignore` na raiz do repo** — adicionar ao final:

```
ingestao/coletores_conhecidos.json
```

- [ ] **Step 9: Commit**

```bash
git add ingestao/__init__.py ingestao/registro_coletores.py ingestao/requirements.txt ingestao/tests/__init__.py ingestao/tests/test_registro_coletores.py .gitignore
git commit -m "feat: registro de coletores conhecidos (chave publica por coletor_id)"
```

---

## Task 2: Validação (parsing + cadeia de hash + assinatura)

**Files:**
- Create: `ingestao/validador.py`
- Test: `ingestao/tests/test_validador.py`

**Interfaces:**
- Consumes: `registro_coletores.obter_chave_publica`, `registro_coletores.registrar_a_partir_de_chave_privada` (Task 1). Em teste apenas: `coletor_simulado.gerador.gerar_dia`, `coletor_simulado.gerador.COLETOR_ID`, `coletor_simulado.identidade.carregar_ou_criar_chave` (fixtures, já existentes de uma rodada anterior).
- Produces: `ResultadoValidacao` (dataclass: `status_validacao`, `motivo_rejeicao`, `total_linhas`, `coletor_id`, `leituras`), `validar_arquivo(caminho, registro_path) -> ResultadoValidacao` — usado pela Task 4.

- [ ] **Step 1: Escrever o teste em `ingestao/tests/test_validador.py`**

```python
from datetime import date

from coletor_simulado import gerador as gerador_simulado
from coletor_simulado import identidade as identidade_simulado
from ingestao import registro_coletores, validador


def _gerar_arquivo_e_registrar(tmp_path, data=date(2026, 7, 18)):
    chave_path = tmp_path / 'chave_coletor.pem'
    output_dir = gerador_simulado.gerar_dia(data, tmp_path / 'output', chave_path=chave_path)
    registro_path = tmp_path / 'registro.json'
    registro_coletores.registrar_a_partir_de_chave_privada(registro_path, chave_path, gerador_simulado.COLETOR_ID)
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_leituras_{data.isoformat()}.txt"
    return caminho_arquivo, registro_path


def test_validar_arquivo_correto(tmp_path):
    caminho_arquivo, registro_path = _gerar_arquivo_e_registrar(tmp_path)
    resultado = validador.validar_arquivo(caminho_arquivo, registro_path)
    assert resultado.status_validacao == 'valido'
    assert resultado.total_linhas == 2880
    assert len(resultado.leituras) == 2880
    assert resultado.coletor_id == gerador_simulado.COLETOR_ID
    assert resultado.motivo_rejeicao is None


def test_validar_arquivo_com_linha_corrompida(tmp_path):
    caminho_arquivo, registro_path = _gerar_arquivo_e_registrar(tmp_path)
    linhas = caminho_arquivo.read_text().split('\n')
    campos = linhas[9].split('|')  # primeira linha de corpo (9 linhas de cabecalho antes)
    campos[5] = '999.9'  # campo 'valor'
    linhas[9] = '|'.join(campos)
    caminho_arquivo.write_text('\n'.join(linhas))

    resultado = validador.validar_arquivo(caminho_arquivo, registro_path)
    assert resultado.status_validacao == 'invalido'
    assert 'hash' in resultado.motivo_rejeicao.lower()
    assert resultado.leituras == []


def test_validar_arquivo_com_chave_errada_registrada(tmp_path):
    caminho_arquivo, registro_path = _gerar_arquivo_e_registrar(tmp_path)
    outra_chave_path = tmp_path / 'outra_chave.pem'
    identidade_simulado.carregar_ou_criar_chave(outra_chave_path)
    registro_coletores.registrar_a_partir_de_chave_privada(registro_path, outra_chave_path, gerador_simulado.COLETOR_ID)

    resultado = validador.validar_arquivo(caminho_arquivo, registro_path)
    assert resultado.status_validacao == 'invalido'
    assert 'assinatura' in resultado.motivo_rejeicao.lower()


def test_validar_arquivo_coletor_nao_registrado(tmp_path):
    chave_path = tmp_path / 'chave_coletor.pem'
    output_dir = gerador_simulado.gerar_dia(date(2026, 7, 18), tmp_path / 'output', chave_path=chave_path)
    registro_path = tmp_path / 'registro_vazio.json'
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_leituras_2026-07-18.txt"

    resultado = validador.validar_arquivo(caminho_arquivo, registro_path)
    assert resultado.status_validacao == 'invalido'
    assert 'não registrado' in resultado.motivo_rejeicao
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python3 -m pytest ingestao/tests/test_validador.py -v`
Expected: `ModuleNotFoundError: No module named 'ingestao.validador'`.

- [ ] **Step 3: Implementar `ingestao/validador.py`**

```python
import base64
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from . import registro_coletores


@dataclass
class ResultadoValidacao:
    status_validacao: str
    motivo_rejeicao: str
    total_linhas: int
    coletor_id: str
    leituras: list = field(default_factory=list)


def _parse_bloco_metadados(linhas):
    metadados = {}
    for linha in linhas:
        if not linha.startswith('#'):
            continue
        chave, _, valor = linha[2:].partition(':')
        metadados[chave.strip()] = valor.strip()
    return metadados


def parse_arquivo(texto):
    linhas = texto.split('\n')
    if linhas and linhas[-1] == '':
        linhas = linhas[:-1]
    idx = 0
    linhas_cabecalho = []
    while idx < len(linhas) and linhas[idx].startswith('#'):
        linhas_cabecalho.append(linhas[idx])
        idx += 1
    linhas_corpo = []
    while idx < len(linhas) and not linhas[idx].startswith('#'):
        linhas_corpo.append(linhas[idx])
        idx += 1
    linhas_rodape = linhas[idx:]
    cabecalho_canonico = '\n'.join(linhas_cabecalho) + '\n'
    metadados_cabecalho = _parse_bloco_metadados(linhas_cabecalho)
    metadados_rodape = _parse_bloco_metadados(linhas_rodape)
    return metadados_cabecalho, cabecalho_canonico, linhas_corpo, metadados_rodape


def parse_linha_leitura(linha):
    campos = linha.split('|')
    (seq, timestamp, sensor_id, area_id, tipo_medida, valor, unidade,
     protocolo_origem, status_leitura, hash_linha) = campos
    linha_sem_hash = '|'.join(campos[:-1])
    return {
        'seq': int(seq),
        'timestamp': timestamp,
        'sensor_id': sensor_id,
        'area_id': area_id,
        'tipo_medida': tipo_medida,
        'valor': float(valor),
        'unidade': unidade,
        'protocolo_origem': protocolo_origem,
        'status_leitura': status_leitura,
        'hash': hash_linha,
        'linha_sem_hash': linha_sem_hash,
    }


def _hash_seed(cabecalho_canonico):
    return hashlib.sha256(cabecalho_canonico.encode()).hexdigest()


def _hash_linha(hash_anterior, linha_sem_hash):
    return hashlib.sha256((hash_anterior + linha_sem_hash).encode()).hexdigest()


def validar_arquivo(caminho, registro_path):
    texto = Path(caminho).read_text()
    metadados_cab, cabecalho_canonico, linhas_corpo, metadados_rod = parse_arquivo(texto)
    coletor_id = metadados_cab.get('coletor_id')
    total_linhas = len(linhas_corpo)

    hash_atual = _hash_seed(cabecalho_canonico)
    leituras = []
    for linha in linhas_corpo:
        parsed = parse_linha_leitura(linha)
        hash_esperado = _hash_linha(hash_atual, parsed['linha_sem_hash'])
        if hash_esperado != parsed['hash']:
            return ResultadoValidacao(
                status_validacao='invalido',
                motivo_rejeicao=f"cadeia de hash quebrada na linha seq={parsed['seq']}",
                total_linhas=total_linhas,
                coletor_id=coletor_id,
            )
        hash_atual = hash_esperado
        leituras.append(parsed)

    hash_final_declarado = metadados_rod.get('hash_final')
    if hash_atual != hash_final_declarado:
        return ResultadoValidacao(
            status_validacao='invalido',
            motivo_rejeicao='hash_final do rodapé não bate com a cadeia recalculada',
            total_linhas=total_linhas,
            coletor_id=coletor_id,
        )

    try:
        chave_publica = registro_coletores.obter_chave_publica(registro_path, coletor_id)
    except KeyError as exc:
        return ResultadoValidacao(
            status_validacao='invalido',
            motivo_rejeicao=str(exc),
            total_linhas=total_linhas,
            coletor_id=coletor_id,
        )

    assinatura = base64.b64decode(metadados_rod.get('assinatura'))
    try:
        chave_publica.verify(assinatura, hash_final_declarado.encode(), ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return ResultadoValidacao(
            status_validacao='invalido',
            motivo_rejeicao='assinatura inválida',
            total_linhas=total_linhas,
            coletor_id=coletor_id,
        )

    return ResultadoValidacao(
        status_validacao='valido',
        motivo_rejeicao=None,
        total_linhas=total_linhas,
        coletor_id=coletor_id,
        leituras=leituras,
    )
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `python3 -m pytest ingestao/tests/test_validador.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add ingestao/validador.py ingestao/tests/test_validador.py
git commit -m "feat: validador de arquivo (parsing, cadeia de hash, assinatura)"
```

---

## Task 3: Gravação no TimescaleDB

**Files:**
- Create: `ingestao/timescale.py`
- Test: `ingestao/tests/test_timescale.py`

**Interfaces:**
- Produces: `conectar(dsn) -> connection`, `inserir_leituras(conn, site_id, coletor_id, leituras) -> int` (quantidade de linhas gravadas) — usado pela Task 4. `leituras` é uma lista de dicts no formato retornado por `validador.parse_linha_leitura` (campos: `timestamp`, `sensor_id`, `area_id`, `tipo_medida`, `valor`, `unidade`, `protocolo_origem`, `status_leitura`).

**Pré-requisito**: TimescaleDB da Fase 1 rodando (`docker compose up -d timescaledb` na raiz do repo, se ainda não estiver).

- [ ] **Step 1: Confirmar que o TimescaleDB está no ar**

Run: `docker compose ps timescaledb` (a partir da raiz do repo)
Expected: serviço `timescaledb` com status `Up`. Se não estiver, rodar `docker compose up -d timescaledb` primeiro.

- [ ] **Step 2: Escrever o teste em `ingestao/tests/test_timescale.py`**

```python
from ingestao import timescale

DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'


def _limpar(site_id):
    conn = timescale.conectar(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sensor_reading WHERE site_id = %s", (site_id,))
        conn.commit()
    finally:
        conn.close()


def test_conectar_e_inserir_leituras():
    site_id = 'SITE-TEST-TIMESCALE'
    _limpar(site_id)
    conn = timescale.conectar(DSN)
    leituras = [
        {
            'timestamp': '2026-07-18T00:00:00-03:00',
            'sensor_id': 'SNR-TEST-001',
            'area_id': 'EXPURGO',
            'tipo_medida': 'temperatura',
            'valor': 19.9,
            'unidade': 'C',
            'protocolo_origem': '4-20mA',
            'status_leitura': 'ok',
        },
    ]
    try:
        total = timescale.inserir_leituras(conn, site_id, 'COL-TEST-001', leituras)
        assert total == 1
        with conn.cursor() as cur:
            cur.execute(
                "SELECT sensor_id, valor FROM sensor_reading WHERE site_id = %s", (site_id,),
            )
            linhas = cur.fetchall()
        assert linhas == [('SNR-TEST-001', 19.9)]
    finally:
        conn.close()
        _limpar(site_id)


def test_inserir_leituras_vazio_retorna_zero():
    conn = timescale.conectar(DSN)
    try:
        total = timescale.inserir_leituras(conn, 'SITE-TEST-VAZIO', 'COL-TEST-001', [])
        assert total == 0
    finally:
        conn.close()
```

- [ ] **Step 3: Rodar os testes e confirmar que falham**

Run: `python3 -m pytest ingestao/tests/test_timescale.py -v`
Expected: `ModuleNotFoundError: No module named 'ingestao.timescale'`.

- [ ] **Step 4: Implementar `ingestao/timescale.py`**

```python
import psycopg2
from psycopg2.extras import execute_values


def conectar(dsn):
    return psycopg2.connect(dsn)


def inserir_leituras(conn, site_id, coletor_id, leituras):
    if not leituras:
        return 0
    valores = [
        (
            leitura['timestamp'], site_id, coletor_id, leitura['sensor_id'],
            leitura['area_id'], leitura['tipo_medida'], leitura['valor'], leitura['unidade'],
            leitura['protocolo_origem'], leitura['status_leitura'],
        )
        for leitura in leituras
    ]
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO sensor_reading
                (time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura)
            VALUES %s
            """,
            valores,
        )
    conn.commit()
    return len(valores)
```

- [ ] **Step 5: Rodar os testes e confirmar que passam**

Run: `python3 -m pytest ingestao/tests/test_timescale.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add ingestao/timescale.py ingestao/tests/test_timescale.py
git commit -m "feat: gravacao em lote de leituras no timescaledb"
```

---

## Task 4: Orquestração (`ingestor.py`) + CLI

**Files:**
- Create: `ingestao/ingestor.py`
- Test: `ingestao/tests/test_ingestor.py`

**Interfaces:**
- Consumes: `validador.validar_arquivo` (Task 2), `timescale.conectar`, `timescale.inserir_leituras` (Task 3). Em teste: `coletor_simulado.gerador.gerar_dia`, `coletor_simulado.gerador.COLETOR_ID`, `registro_coletores.registrar_a_partir_de_chave_privada` (Task 1).
- Produces: `ResultadoIngestao` (classe simples: `status_validacao`, `motivo_rejeicao`, `total_linhas`, `total_gravado`), `ingerir_arquivo(caminho, registro_path, dsn, site_id) -> ResultadoIngestao`. CLI: `python -m ingestao.ingestor --arquivo <path> --registro <path> --site-id <id> [--dsn <dsn>]`.

**Pré-requisito**: TimescaleDB rodando (mesmo da Task 3).

- [ ] **Step 1: Escrever o teste em `ingestao/tests/test_ingestor.py`**

```python
from datetime import date

from coletor_simulado import gerador as gerador_simulado
from ingestao import ingestor, registro_coletores, timescale

DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'


def _limpar(site_id):
    conn = timescale.conectar(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sensor_reading WHERE site_id = %s", (site_id,))
        conn.commit()
    finally:
        conn.close()


def test_ingerir_arquivo_valido_grava_no_timescale(tmp_path):
    site_id = 'SITE-TEST-INGESTOR-OK'
    chave_path = tmp_path / 'chave.pem'
    output_dir = gerador_simulado.gerar_dia(date(2026, 7, 19), tmp_path / 'output', chave_path=chave_path)
    registro_path = tmp_path / 'registro.json'
    registro_coletores.registrar_a_partir_de_chave_privada(registro_path, chave_path, gerador_simulado.COLETOR_ID)
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_leituras_2026-07-19.txt"

    _limpar(site_id)
    try:
        resultado = ingestor.ingerir_arquivo(caminho_arquivo, registro_path, DSN, site_id)
        assert resultado.status_validacao == 'valido'
        assert resultado.total_linhas == 2880
        assert resultado.total_gravado == 2880
    finally:
        _limpar(site_id)


def test_ingerir_arquivo_corrompido_nao_grava_nada(tmp_path):
    site_id = 'SITE-TEST-INGESTOR-BAD'
    chave_path = tmp_path / 'chave.pem'
    output_dir = gerador_simulado.gerar_dia(date(2026, 7, 20), tmp_path / 'output', chave_path=chave_path)
    registro_path = tmp_path / 'registro.json'
    registro_coletores.registrar_a_partir_de_chave_privada(registro_path, chave_path, gerador_simulado.COLETOR_ID)
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_leituras_2026-07-20.txt"
    linhas = caminho_arquivo.read_text().split('\n')
    campos = linhas[9].split('|')
    campos[5] = '999.9'
    linhas[9] = '|'.join(campos)
    caminho_arquivo.write_text('\n'.join(linhas))

    _limpar(site_id)
    try:
        resultado = ingestor.ingerir_arquivo(caminho_arquivo, registro_path, DSN, site_id)
        assert resultado.status_validacao == 'invalido'
        assert resultado.total_gravado == 0
        with_conn = timescale.conectar(DSN)
        try:
            with with_conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM sensor_reading WHERE site_id = %s", (site_id,))
                (total,) = cur.fetchone()
            assert total == 0
        finally:
            with_conn.close()
    finally:
        _limpar(site_id)
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python3 -m pytest ingestao/tests/test_ingestor.py -v`
Expected: `ModuleNotFoundError: No module named 'ingestao.ingestor'`.

- [ ] **Step 3: Implementar `ingestao/ingestor.py`**

```python
import argparse
from dataclasses import dataclass

from . import timescale, validador


@dataclass
class ResultadoIngestao:
    status_validacao: str
    motivo_rejeicao: str
    total_linhas: int
    total_gravado: int


def ingerir_arquivo(caminho, registro_path, dsn, site_id):
    resultado_validacao = validador.validar_arquivo(caminho, registro_path)
    if resultado_validacao.status_validacao != 'valido':
        return ResultadoIngestao(
            status_validacao=resultado_validacao.status_validacao,
            motivo_rejeicao=resultado_validacao.motivo_rejeicao,
            total_linhas=resultado_validacao.total_linhas,
            total_gravado=0,
        )
    conn = timescale.conectar(dsn)
    try:
        total_gravado = timescale.inserir_leituras(
            conn, site_id, resultado_validacao.coletor_id, resultado_validacao.leituras,
        )
    finally:
        conn.close()
    return ResultadoIngestao(
        status_validacao='valido',
        motivo_rejeicao=None,
        total_linhas=resultado_validacao.total_linhas,
        total_gravado=total_gravado,
    )


def main():
    parser = argparse.ArgumentParser(description='Ingestão de arquivo de leituras do coletor simulado')
    parser.add_argument('--arquivo', required=True)
    parser.add_argument('--registro', default='ingestao/coletores_conhecidos.json')
    parser.add_argument('--site-id', required=True, dest='site_id')
    parser.add_argument('--dsn', default='postgresql://sentinela:sentinela@localhost:5433/sentinela')
    args = parser.parse_args()
    resultado = ingerir_arquivo(args.arquivo, args.registro, args.dsn, args.site_id)
    print(
        f"status={resultado.status_validacao} total_linhas={resultado.total_linhas} "
        f"total_gravado={resultado.total_gravado} motivo={resultado.motivo_rejeicao}"
    )


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `python3 -m pytest ingestao/tests/test_ingestor.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add ingestao/ingestor.py ingestao/tests/test_ingestor.py
git commit -m "feat: orquestracao da ingestao (validar+gravar) e CLI"
```

---

## Task 5: Verificação final (suíte completa + fluxo real ponta a ponta)

**Files:**
- Modify: nenhum arquivo novo — task de verificação/fechamento.

**Interfaces:**
- Consumes: tudo das Tasks 1–4, mais `coletor_simulado/` (rodada anterior).

- [ ] **Step 1: Confirmar TimescaleDB no ar e rodar a suíte completa**

Run (a partir da raiz do repo):
```bash
docker compose up -d timescaledb
python3 -m venv .venv && source .venv/bin/activate
pip install -r coletor_simulado/requirements.txt -r ingestao/requirements.txt
python3 -m pytest coletor_simulado/tests/ ingestao/tests/ -v
```
Expected: todos os testes de `coletor_simulado` (14, já existentes) + todos os de `ingestao` (13: 5+4+2+2) passam — 0 failed.

- [ ] **Step 2: Fluxo real ponta a ponta — gerar arquivo, registrar chave, ingerir**

Run:
```bash
python3 -m coletor_simulado.gerador --data 2026-07-18 --output-dir coletor_simulado/output --injetar-alarme
python3 -m ingestao.registro_coletores --registrar COL-SIM-0001 --a-partir-de coletor_simulado/identidade/coletor_privkey.pem --registro ingestao/coletores_conhecidos.json
python3 -m ingestao.ingestor --arquivo coletor_simulado/output/COL-SIM-0001_leituras_2026-07-18.txt --registro ingestao/coletores_conhecidos.json --site-id SITE-SIM-0001
```
Expected: última linha imprime `status=valido total_linhas=2880 total_gravado=2880 motivo=None`.

- [ ] **Step 3: Confirmar os dados no TimescaleDB via SQL direto**

Run:
```bash
docker compose exec timescaledb psql -U sentinela -d sentinela -c "SELECT count(*), min(time), max(time) FROM sensor_reading WHERE site_id = 'SITE-SIM-0001';"
```
Expected: `count = 2880`, `min`/`max` cobrindo o dia 2026-07-18 (00:00 a 23:59, horário `-03:00`).

- [ ] **Step 4: Limpar os dados de teste gravados no Step 2/3 (não são fixture de teste automatizado, ficariam órfãos no banco de dev)**

Run:
```bash
docker compose exec timescaledb psql -U sentinela -d sentinela -c "DELETE FROM sensor_reading WHERE site_id = 'SITE-SIM-0001';"
```
Expected: `DELETE 2880`.

- [ ] **Step 5: Commit final (se houver qualquer ajuste feito durante a verificação)**

```bash
git add -A
git commit -m "chore: verificacao final do servico de ingestao" --allow-empty
```
