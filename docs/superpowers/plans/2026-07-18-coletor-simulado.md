# Coletor Simulado Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Script Python standalone que gera, localmente, um par de arquivos diários (`leituras` + `alarmes`) no formato exato de `esp32_coletor_spec.md` §4/5, assinados com uma chave ECDSA persistida (simulando o secure element do coletor real).

**Architecture:** Três módulos puros (`identidade.py` — chave/assinatura, `formato.py` — construção de linha/cabeçalho/rodapé/cadeia de hash, `gerador.py` — orquestração + CLI), sem dependência de Odoo, banco ou rede. Saída: dois arquivos `.txt` em disco.

**Tech Stack:** Python 3, `cryptography` (ECDSA P-256), `pytest`.

## Global Constraints

- Sem MQTT, sem SFTP, sem serviço de ingestão nesta rodada — só o gerador de arquivo (ver spec, seção "Escopo desta rodada").
- Formato de arquivo exatamente conforme `esp32_coletor_spec.md` §4 (leituras) e §5 (alarmes) — cabeçalho, corpo `|`-delimitado, rodapé com `hash_final`+`assinatura`.
- Cadeia de hash: `hash_0 = SHA256(cabeçalho_canônico)`, `hash_n = SHA256(hash_(n-1) + linha_n_sem_hash)` — não atravessa arquivos (leituras e alarmes têm cadeias independentes).
- Assinatura ECDSA (curva `SECP256R1`/P-256, hash SHA-256) sobre o `hash_final` — uma operação por arquivo.
- Identificadores (`coletor_id`, `hub_id`, `sensor_id`, `area_id`) nunca podem conter `|`, `\n`, `\r` (mesma regra do módulo Odoo).
- Cenário fixo: 1 coletor (`COL-SIM-0001`), 2 sensores na área `EXPURGO` — `SNR-SIM-TEMP-01` (temperatura) e `SNR-SIM-PRES-01` (pressão diferencial), limiares RDC15 do Expurgo (18–22°C / pressão negativa mín. 2,5Pa).
- Arquivo de alarme sempre gerado e assinado, mesmo com `total_eventos: 0`.

---

## Task 1: Estrutura do projeto + identidade (chave ECDSA, fingerprint, assinatura)

**Files:**
- Create: `coletor_simulado/__init__.py`
- Create: `coletor_simulado/identidade.py`
- Create: `coletor_simulado/requirements.txt`
- Create: `coletor_simulado/tests/__init__.py`
- Test: `coletor_simulado/tests/test_identidade.py`
- Modify: `.gitignore` (raiz do repo)

**Interfaces:**
- Produces: `carregar_ou_criar_chave(caminho) -> EllipticCurvePrivateKey`, `fingerprint_publica(chave_privada) -> str`, `assinar(chave_privada, dado_bytes) -> bytes`, `verificar_assinatura(chave_publica, assinatura, dado_bytes) -> None` (levanta `cryptography.exceptions.InvalidSignature` se inválida) — todos em `coletor_simulado/identidade.py`, usados pela Task 3.

- [ ] **Step 1: Criar `coletor_simulado/requirements.txt`**

```
cryptography>=42
pytest>=8
```

- [ ] **Step 2: Criar `coletor_simulado/__init__.py`** (vazio)

- [ ] **Step 3: Criar `coletor_simulado/tests/__init__.py`** (vazio)

- [ ] **Step 4: Escrever o teste em `coletor_simulado/tests/test_identidade.py`**

```python
import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ec

from coletor_simulado import identidade


def test_chave_persiste_entre_chamadas(tmp_path):
    caminho = tmp_path / "chave.pem"
    chave1 = identidade.carregar_ou_criar_chave(caminho)
    chave2 = identidade.carregar_ou_criar_chave(caminho)
    assert chave1.private_numbers().private_value == chave2.private_numbers().private_value


def test_fingerprint_deterministico(tmp_path):
    caminho = tmp_path / "chave.pem"
    chave = identidade.carregar_ou_criar_chave(caminho)
    fp1 = identidade.fingerprint_publica(chave)
    fp2 = identidade.fingerprint_publica(chave)
    assert fp1 == fp2
    assert len(fp1.split(':')) == 32  # SHA-256 = 32 bytes


def test_assinatura_verifica_com_chave_correta(tmp_path):
    caminho = tmp_path / "chave.pem"
    chave = identidade.carregar_ou_criar_chave(caminho)
    dado = b"hash_final_de_teste"
    assinatura = identidade.assinar(chave, dado)
    identidade.verificar_assinatura(chave.public_key(), assinatura, dado)


def test_assinatura_falha_com_chave_errada(tmp_path):
    caminho = tmp_path / "chave.pem"
    chave = identidade.carregar_ou_criar_chave(caminho)
    outra_chave = ec.generate_private_key(ec.SECP256R1())
    dado = b"hash_final_de_teste"
    assinatura = identidade.assinar(chave, dado)
    with pytest.raises(InvalidSignature):
        identidade.verificar_assinatura(outra_chave.public_key(), assinatura, dado)
```

- [ ] **Step 5: Rodar os testes e confirmar que falham**

Run: `python3 -m pytest coletor_simulado/tests/test_identidade.py -v`
Expected: `ModuleNotFoundError: No module named 'coletor_simulado.identidade'` (ou `ImportError`).

- [ ] **Step 6: Implementar `coletor_simulado/identidade.py`**

```python
import hashlib
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


def carregar_ou_criar_chave(caminho):
    caminho = Path(caminho)
    if caminho.exists():
        return serialization.load_pem_private_key(caminho.read_bytes(), password=None)
    chave = ec.generate_private_key(ec.SECP256R1())
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(chave.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    return chave


def fingerprint_publica(chave_privada):
    chave_publica_der = chave_privada.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    digest = hashlib.sha256(chave_publica_der).hexdigest().upper()
    return ':'.join(digest[i:i + 2] for i in range(0, len(digest), 2))


def assinar(chave_privada, dado_bytes):
    return chave_privada.sign(dado_bytes, ec.ECDSA(hashes.SHA256()))


def verificar_assinatura(chave_publica, assinatura, dado_bytes):
    chave_publica.verify(assinatura, dado_bytes, ec.ECDSA(hashes.SHA256()))
```

- [ ] **Step 7: Rodar os testes e confirmar que passam**

Run: `python3 -m pytest coletor_simulado/tests/test_identidade.py -v`
Expected: 4 passed.

- [ ] **Step 8: Atualizar `.gitignore` na raiz do repo** — adicionar ao final:

```
coletor_simulado/identidade/
coletor_simulado/output/
```

- [ ] **Step 9: Commit**

```bash
git add coletor_simulado/__init__.py coletor_simulado/identidade.py coletor_simulado/requirements.txt coletor_simulado/tests/__init__.py coletor_simulado/tests/test_identidade.py .gitignore
git commit -m "feat: identidade do coletor simulado (chave ECDSA, fingerprint, assinatura)"
```

---

## Task 2: Formato de arquivo (cabeçalho, cadeia de hash, linhas, rodapé)

**Files:**
- Create: `coletor_simulado/formato.py`
- Test: `coletor_simulado/tests/test_formato.py`
- Modify: `coletor_simulado/tests/__init__.py`

**Interfaces:**
- Produces: `montar_cabecalho(tipo_arquivo, coletor_id, hub_id, pubkey_fingerprint, data_referencia, timezone_offset, firmware_version) -> str`, `hash_seed(cabecalho_canonico) -> str`, `hash_linha(hash_anterior, linha_sem_hash) -> str`, `gerar_linha_leitura(hash_anterior, seq, timestamp, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura) -> tuple[str, str]` (linha completa, novo hash), `gerar_linha_alarme(hash_anterior, seq, timestamp, sensor_id, area_id, tipo_medida, tipo_evento, tipo_violacao, valor, limite_min_vigente, limite_max_vigente) -> tuple[str, str]`, `montar_rodape(total, hash_final, assinatura_b64, campo_total) -> str`, `validar_identificador(valor) -> None` (levanta `ValueError`) — todos usados pela Task 3.

- [ ] **Step 1: Escrever o teste em `coletor_simulado/tests/test_formato.py`**

```python
import pytest

from coletor_simulado import formato


def test_hash_seed_determinismo():
    cab = "# schema_version: 1\n# tipo_arquivo: leituras\n"
    assert formato.hash_seed(cab) == formato.hash_seed(cab)
    assert formato.hash_seed(cab) != formato.hash_seed(cab + "x")


def test_cadeia_hash_encadeia_linhas_e_bate_com_recalculo():
    cab = formato.montar_cabecalho('leituras', 'COL-1', 'HUB-1', 'AA:BB', '2026-07-18', '-03:00', '1.0.0')
    h0 = formato.hash_seed(cab)
    linha1, h1 = formato.gerar_linha_leitura(
        h0, 1, '2026-07-18T00:01:00-03:00', 'SNR-1', 'EXPURGO', 'temperatura', 19.8, 'C', '4-20ma', 'ok',
    )
    linha2, h2 = formato.gerar_linha_leitura(
        h1, 2, '2026-07-18T00:02:00-03:00', 'SNR-1', 'EXPURGO', 'temperatura', 19.9, 'C', '4-20ma', 'ok',
    )
    assert h1 != h2
    assert linha1.endswith(h1)
    assert linha1.split('|')[0] == '1'
    campos_sem_hash = '1|2026-07-18T00:01:00-03:00|SNR-1|EXPURGO|temperatura|19.8|C|4-20ma|ok'
    assert formato.hash_linha(h0, campos_sem_hash) == h1


def test_validar_identificador_rejeita_caracteres_proibidos():
    with pytest.raises(ValueError):
        formato.validar_identificador('SNR|001')
    with pytest.raises(ValueError):
        formato.validar_identificador('SNR\n001')
    with pytest.raises(ValueError):
        formato.validar_identificador('SNR\r001')
    formato.validar_identificador('SNR-001')  # não levanta


def test_linha_alarme_usa_travessao_quando_limite_ausente():
    linha, h = formato.gerar_linha_alarme(
        'seed', 1, '2026-07-18T02:00:00-03:00', 'SNR-PRES', 'EXPURGO', 'pressao_diferencial',
        'entrada_alarme', 'acima_limite', 1.0, None, -2.5,
    )
    campos = linha.split('|')
    assert campos[8] == '—'
    assert campos[9] == '-2.5'


def test_montar_rodape_leituras():
    rodape = formato.montar_rodape(2880, 'abc123', 'ZmFrZQ==', 'total_linhas')
    assert '# total_linhas: 2880' in rodape
    assert '# hash_final: abc123' in rodape
    assert '# assinatura: ZmFrZQ==' in rodape
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python3 -m pytest coletor_simulado/tests/test_formato.py -v`
Expected: `ModuleNotFoundError: No module named 'coletor_simulado.formato'`.

- [ ] **Step 3: Implementar `coletor_simulado/formato.py`**

```python
import hashlib

CARACTERES_PROIBIDOS = ('|', '\n', '\r')


def validar_identificador(valor):
    if any(c in valor for c in CARACTERES_PROIBIDOS):
        raise ValueError(f"identificador '{valor}' contém caractere proibido (|, \\n ou \\r)")


def montar_cabecalho(tipo_arquivo, coletor_id, hub_id, pubkey_fingerprint, data_referencia, timezone_offset, firmware_version):
    for valor in (coletor_id, hub_id):
        validar_identificador(valor)
    linhas = [
        "# schema_version: 1",
        f"# tipo_arquivo: {tipo_arquivo}",
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


def hash_seed(cabecalho_canonico):
    return hashlib.sha256(cabecalho_canonico.encode()).hexdigest()


def hash_linha(hash_anterior, linha_sem_hash):
    return hashlib.sha256((hash_anterior + linha_sem_hash).encode()).hexdigest()


def gerar_linha_leitura(hash_anterior, seq, timestamp, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura):
    for identificador in (sensor_id, area_id):
        validar_identificador(identificador)
    campos_sem_hash = [str(seq), timestamp, sensor_id, area_id, tipo_medida, str(valor), unidade, protocolo_origem, status_leitura]
    linha_sem_hash = '|'.join(campos_sem_hash)
    novo_hash = hash_linha(hash_anterior, linha_sem_hash)
    return linha_sem_hash + '|' + novo_hash, novo_hash


def gerar_linha_alarme(hash_anterior, seq, timestamp, sensor_id, area_id, tipo_medida, tipo_evento, tipo_violacao, valor, limite_min_vigente, limite_max_vigente):
    for identificador in (sensor_id, area_id):
        validar_identificador(identificador)

    def fmt_limite(v):
        return '—' if v is None else str(v)

    campos_sem_hash = [
        str(seq), timestamp, sensor_id, area_id, tipo_medida, tipo_evento, tipo_violacao,
        str(valor), fmt_limite(limite_min_vigente), fmt_limite(limite_max_vigente),
    ]
    linha_sem_hash = '|'.join(campos_sem_hash)
    novo_hash = hash_linha(hash_anterior, linha_sem_hash)
    return linha_sem_hash + '|' + novo_hash, novo_hash


def montar_rodape(total, hash_final, assinatura_b64, campo_total):
    return (
        f"# {campo_total}: {total}\n"
        f"# hash_final: {hash_final}\n"
        f"# assinatura: {assinatura_b64}\n"
    )
```

- [ ] **Step 4: Atualizar `coletor_simulado/tests/__init__.py`** (permanece vazio — os testes são descobertos pelo pytest via nome de arquivo, sem necessidade de import explícito)

- [ ] **Step 5: Rodar os testes e confirmar que passam**

Run: `python3 -m pytest coletor_simulado/tests/test_formato.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add coletor_simulado/formato.py coletor_simulado/tests/test_formato.py
git commit -m "feat: formato de arquivo do coletor simulado (cabecalho, cadeia de hash, linhas, rodape)"
```

---

## Task 3: Gerador (leituras + alarmes do dia) + CLI

**Files:**
- Create: `coletor_simulado/gerador.py`
- Test: `coletor_simulado/tests/test_gerador.py`

**Interfaces:**
- Consumes: `identidade.carregar_ou_criar_chave`, `identidade.fingerprint_publica`, `identidade.assinar`, `identidade.verificar_assinatura` (Task 1); `formato.montar_cabecalho`, `formato.hash_seed`, `formato.gerar_linha_leitura`, `formato.gerar_linha_alarme`, `formato.montar_rodape` (Task 2).
- Produces: `gerar_dia(data, output_dir, injetar_alarme=False, chave_path=None) -> Path` — grava `<coletor_id>_leituras_<data>.txt` e `<coletor_id>_alarmes_<data>.txt` em `output_dir`, retorna o `Path` de `output_dir`. CLI via `python -m coletor_simulado.gerador --data YYYY-MM-DD --output-dir DIR [--injetar-alarme]`.

- [ ] **Step 1: Escrever o teste em `coletor_simulado/tests/test_gerador.py`**

```python
import base64
from datetime import date

from coletor_simulado import gerador, identidade


def test_gerar_dia_sem_alarme(tmp_path):
    chave_path = tmp_path / 'chave.pem'
    output_dir = gerador.gerar_dia(date(2026, 7, 18), tmp_path / 'output', injetar_alarme=False, chave_path=chave_path)
    leituras = (output_dir / 'COL-SIM-0001_leituras_2026-07-18.txt').read_text()
    alarmes = (output_dir / 'COL-SIM-0001_alarmes_2026-07-18.txt').read_text()
    assert '# total_linhas: 2880' in leituras
    assert '# total_eventos: 0' in alarmes
    assert '# tipo_arquivo: leituras' in leituras
    assert '# tipo_arquivo: alarmes' in alarmes


def test_gerar_dia_com_alarme_injeta_par_entrada_saida(tmp_path):
    chave_path = tmp_path / 'chave.pem'
    output_dir = gerador.gerar_dia(date(2026, 7, 18), tmp_path / 'output', injetar_alarme=True, chave_path=chave_path)
    alarmes = (output_dir / 'COL-SIM-0001_alarmes_2026-07-18.txt').read_text()
    assert '# total_eventos: 2' in alarmes
    assert 'entrada_alarme' in alarmes
    assert 'saida_alarme' in alarmes
    assert 'T02:00:00' in alarmes
    assert 'T02:07:00' in alarmes


def test_assinatura_do_rodape_de_leituras_verifica(tmp_path):
    chave_path = tmp_path / 'chave.pem'
    output_dir = gerador.gerar_dia(date(2026, 7, 18), tmp_path / 'output', chave_path=chave_path)
    chave = identidade.carregar_ou_criar_chave(chave_path)
    conteudo = (output_dir / 'COL-SIM-0001_leituras_2026-07-18.txt').read_text()
    linhas = conteudo.strip().split('\n')
    hash_final = next(l for l in linhas if l.startswith('# hash_final:')).split(': ', 1)[1]
    assinatura_b64 = next(l for l in linhas if l.startswith('# assinatura:')).split(': ', 1)[1]
    assinatura = base64.b64decode(assinatura_b64)
    identidade.verificar_assinatura(chave.public_key(), assinatura, hash_final.encode())


def test_chave_persiste_entre_execucoes(tmp_path):
    chave_path = tmp_path / 'chave.pem'
    gerador.gerar_dia(date(2026, 7, 18), tmp_path / 'output1', chave_path=chave_path)
    gerador.gerar_dia(date(2026, 7, 19), tmp_path / 'output2', chave_path=chave_path)
    conteudo1 = (tmp_path / 'output1' / 'COL-SIM-0001_leituras_2026-07-18.txt').read_text()
    conteudo2 = (tmp_path / 'output2' / 'COL-SIM-0001_leituras_2026-07-19.txt').read_text()
    fingerprint1 = next(l for l in conteudo1.split('\n') if 'pubkey_fingerprint' in l)
    fingerprint2 = next(l for l in conteudo2.split('\n') if 'pubkey_fingerprint' in l)
    assert fingerprint1 == fingerprint2
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python3 -m pytest coletor_simulado/tests/test_gerador.py -v`
Expected: `ModuleNotFoundError: No module named 'coletor_simulado.gerador'`.

- [ ] **Step 3: Implementar `coletor_simulado/gerador.py`**

```python
import argparse
import base64
import random
from datetime import date as date_cls, datetime, timedelta
from pathlib import Path

from . import formato, identidade

SENSORES = [
    {'sensor_id': 'SNR-SIM-TEMP-01', 'tipo_medida': 'temperatura', 'unidade': 'C'},
    {'sensor_id': 'SNR-SIM-PRES-01', 'tipo_medida': 'pressao_diferencial', 'unidade': 'Pa'},
]
AREA_ID = 'EXPURGO'
COLETOR_ID = 'COL-SIM-0001'
HUB_ID = 'HUB-SIM-0001'
PROTOCOLO_ORIGEM = '4-20ma'
FIRMWARE_VERSION = '0.1.0-sim'
TIMEZONE_OFFSET = '-03:00'
LIMITE_MIN_PRESSAO_VIGENTE = None
LIMITE_MAX_PRESSAO_VIGENTE = -2.5
MINUTO_INICIO_ALARME = 120  # 02:00
MINUTO_FIM_ALARME = 127  # 02:07 (primeiro minuto de volta ao normal)


def _timestamp(data, minuto):
    dt = datetime.combine(data, datetime.min.time()) + timedelta(minutes=minuto)
    return dt.strftime('%Y-%m-%dT%H:%M:%S') + TIMEZONE_OFFSET


def _valor_para_sensor(sensor, minuto, injetar_alarme):
    if sensor['tipo_medida'] == 'temperatura':
        return round(random.gauss(20.0, 0.6), 1)
    if injetar_alarme and MINUTO_INICIO_ALARME <= minuto < MINUTO_FIM_ALARME:
        return round(random.gauss(1.0, 0.1), 1)
    return round(random.gauss(-3.5, 0.3), 1)


def montar_corpo_leituras(cabecalho, data, injetar_alarme=False):
    hash_atual = formato.hash_seed(cabecalho)
    linhas = []
    seq = 1
    for minuto in range(24 * 60):
        timestamp = _timestamp(data, minuto)
        for sensor in SENSORES:
            valor = _valor_para_sensor(sensor, minuto, injetar_alarme)
            linha, hash_atual = formato.gerar_linha_leitura(
                hash_atual, seq, timestamp, sensor['sensor_id'], AREA_ID,
                sensor['tipo_medida'], valor, sensor['unidade'], PROTOCOLO_ORIGEM, 'ok',
            )
            linhas.append(linha)
            seq += 1
    return linhas, hash_atual


def montar_corpo_alarmes(cabecalho, data, injetar_alarme=False):
    hash_atual = formato.hash_seed(cabecalho)
    linhas = []
    if not injetar_alarme:
        return linhas, hash_atual
    sensor_pressao = SENSORES[1]
    linha1, hash_atual = formato.gerar_linha_alarme(
        hash_atual, 1, _timestamp(data, MINUTO_INICIO_ALARME), sensor_pressao['sensor_id'], AREA_ID,
        sensor_pressao['tipo_medida'], 'entrada_alarme', 'acima_limite', 1.0,
        LIMITE_MIN_PRESSAO_VIGENTE, LIMITE_MAX_PRESSAO_VIGENTE,
    )
    linhas.append(linha1)
    linha2, hash_atual = formato.gerar_linha_alarme(
        hash_atual, 2, _timestamp(data, MINUTO_FIM_ALARME), sensor_pressao['sensor_id'], AREA_ID,
        sensor_pressao['tipo_medida'], 'saida_alarme', 'acima_limite', -3.5,
        LIMITE_MIN_PRESSAO_VIGENTE, LIMITE_MAX_PRESSAO_VIGENTE,
    )
    linhas.append(linha2)
    return linhas, hash_atual


def gerar_dia(data, output_dir, injetar_alarme=False, chave_path=None):
    chave_path = Path(chave_path) if chave_path else Path(__file__).parent / 'identidade' / 'coletor_privkey.pem'
    chave = identidade.carregar_ou_criar_chave(chave_path)
    fingerprint = identidade.fingerprint_publica(chave)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    geradores_de_corpo = (
        ('leituras', montar_corpo_leituras, 'total_linhas'),
        ('alarmes', montar_corpo_alarmes, 'total_eventos'),
    )
    for tipo_arquivo, montar_corpo, campo_total in geradores_de_corpo:
        cabecalho = formato.montar_cabecalho(
            tipo_arquivo, COLETOR_ID, HUB_ID, fingerprint,
            data.isoformat(), TIMEZONE_OFFSET, FIRMWARE_VERSION,
        )
        linhas, hash_final = montar_corpo(cabecalho, data, injetar_alarme)
        assinatura = identidade.assinar(chave, hash_final.encode())
        assinatura_b64 = base64.b64encode(assinatura).decode()
        rodape = formato.montar_rodape(len(linhas), hash_final, assinatura_b64, campo_total)
        corpo = '\n'.join(linhas) + ('\n' if linhas else '')
        conteudo = cabecalho + corpo + rodape
        nome_arquivo = f"{COLETOR_ID}_{tipo_arquivo}_{data.isoformat()}.txt"
        (output_dir / nome_arquivo).write_text(conteudo)
    return output_dir


def main():
    parser = argparse.ArgumentParser(description='Coletor simulado — gera arquivos assinados de leituras/alarmes')
    parser.add_argument('--data', type=str, default=None, help='YYYY-MM-DD (default: hoje)')
    parser.add_argument('--output-dir', type=str, default='./output')
    parser.add_argument('--injetar-alarme', action='store_true')
    args = parser.parse_args()
    data = date_cls.fromisoformat(args.data) if args.data else date_cls.today()
    output_dir = gerar_dia(data, args.output_dir, args.injetar_alarme)
    print(f"Arquivos gerados em {output_dir}")


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `python3 -m pytest coletor_simulado/tests/test_gerador.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add coletor_simulado/gerador.py coletor_simulado/tests/test_gerador.py
git commit -m "feat: gerador do coletor simulado (leituras+alarmes do dia) e CLI"
```

---

## Task 4: Verificação final (suíte completa + execução real da CLI)

**Files:**
- Modify: nenhum arquivo novo — task de verificação/fechamento.

**Interfaces:**
- Consumes: tudo das Tasks 1–3.

- [ ] **Step 1: Instalar dependências e rodar a suíte completa**

Run (a partir da raiz do repo — os módulos usam `from coletor_simulado import ...`, então o pacote precisa ser resolvido a partir do diretório pai, nunca de dentro de `coletor_simulado/`):
```bash
cd /home/afonso/docker/odoo_sentinela
python3 -m venv .venv && source .venv/bin/activate
pip install -r coletor_simulado/requirements.txt
python3 -m pytest coletor_simulado/tests/ -v
```
Expected: 13 passed (4 identidade + 5 formato + 4 gerador), 0 failed.

- [ ] **Step 2: Rodar a CLI de verdade (fora do pytest) e inspecionar o arquivo gerado**

Run (mesma raiz do repo, mesmo motivo — `python -m coletor_simulado.gerador`, não `cd coletor_simulado && python -m gerador`):
```bash
cd /home/afonso/docker/odoo_sentinela
python3 -m coletor_simulado.gerador --data 2026-07-18 --output-dir coletor_simulado/output --injetar-alarme
ls -la coletor_simulado/output/
head -12 coletor_simulado/output/COL-SIM-0001_leituras_2026-07-18.txt
cat coletor_simulado/output/COL-SIM-0001_alarmes_2026-07-18.txt
```
Expected: dois arquivos `.txt` criados em `coletor_simulado/output/`; o de leituras com cabeçalho de 9 linhas seguido de linhas `seq|timestamp|...`; o de alarmes com exatamente 2 linhas de evento (`entrada_alarme`/`saida_alarme`) entre cabeçalho e rodapé.

- [ ] **Step 3: Confirmar que a chave privada e a saída não foram versionadas**

Run: `cd /home/afonso/docker/odoo_sentinela && git status --short coletor_simulado/`
Expected: nenhum arquivo dentro de `coletor_simulado/identidade/` ou `coletor_simulado/output/` aparece (cobertos pelo `.gitignore` da Task 1).

- [ ] **Step 4: Commit final (se houver qualquer ajuste feito durante a verificação)**

```bash
git add -A
git commit -m "chore: verificacao final do coletor simulado" --allow-empty
```
