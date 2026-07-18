# Integração Odoo (resolução de site + file.ledger) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O serviço de ingestão passa a consultar o Odoo (XML-RPC) para resolver o `site_code` real a partir do `coletor_id` do arquivo, e a gravar um `sensor_monitor.file.ledger` refletindo o resultado — válido ou inválido.

**Architecture:** Novo módulo `ingestao/odoo_cliente.py` (cliente XML-RPC fino, stdlib) + script de provisionamento idempotente `ingestao/provisionar_odoo_sim.py` (cria o cadastro do cenário simulado no Odoo) + extensão de `validador.py` (3 campos novos no resultado) + reescrita de `ingestor.py` (troca `site_id` fixo por consulta ao Odoo + grava ledger).

**Tech Stack:** Python 3 stdlib `xmlrpc.client` (sem lib nova), Odoo 18 já rodando (`http://localhost:8189`, banco `sentinela`).

## Global Constraints

- Credenciais Odoo (dev, confirmadas funcionais nesta sessão): usuário `admin`, senha `admin`, banco `sentinela`, URL `http://localhost:8189`.
- Sem arquivo de alarmes, sem `alarm.event`, sem usuário de serviço dedicado nesta rodada.
- Provisionamento do cenário simulado é **idempotente** (busca por código antes de criar) — nunca duplica ao rodar de novo.
- `escrever_ledger` também é idempotente por (coletor, data, tipo) — reflete a constraint de unicidade já existente no modelo Odoo (`sensor_monitor.file.ledger`, Fase 1).
- Não tocar no cadastro manual existente (`CMEOX-01`/`COL-01`/`TEMP-01`) — usado só como fixture de teste para provar que `resolver_coletor` funciona contra dado real pré-existente.

---

## Task 1: Cliente Odoo (conectar + executar + resolver_coletor)

**Files:**
- Create: `ingestao/odoo_cliente.py`
- Test: `ingestao/tests/test_odoo_cliente.py`

**Interfaces:**
- Produces: `ClienteOdoo` (classe: `db`, `senha`, `uid`, `models`), `conectar(url, db, usuario, senha) -> ClienteOdoo` (levanta `RuntimeError` se autenticação falhar), `executar(cliente, model, metodo, *args, **kwargs)` (wrapper sobre `execute_kw`), `resolver_coletor(cliente, coletor_code) -> dict` (`{'id', 'hub_id', 'site_id', 'site_code'}`, levanta `ValueError` se não encontrado) — usados pelas Tasks 2, 4, 5.

**Pré-requisito**: Odoo rodando em `http://localhost:8189` (banco `sentinela`) com o coletor `COL-01` já cadastrado (cadastro manual, já existe).

- [ ] **Step 1: Confirmar que o Odoo está no ar e as credenciais funcionam**

Run:
```bash
python3 -c "
import xmlrpc.client
common = xmlrpc.client.ServerProxy('http://localhost:8189/xmlrpc/2/common')
uid = common.authenticate('sentinela', 'admin', 'admin', {})
print('uid:', uid)
"
```
Expected: `uid: 2` (ou outro inteiro positivo — qualquer uid válido serve).

- [ ] **Step 2: Escrever o teste em `ingestao/tests/test_odoo_cliente.py`**

```python
import pytest

from ingestao import odoo_cliente

ODOO_URL = 'http://localhost:8189'
ODOO_DB = 'sentinela'
ODOO_USUARIO = 'admin'
ODOO_SENHA = 'admin'


@pytest.fixture
def cliente():
    return odoo_cliente.conectar(ODOO_URL, ODOO_DB, ODOO_USUARIO, ODOO_SENHA)


def test_conectar_autentica_com_sucesso(cliente):
    assert cliente.uid


def test_conectar_falha_com_credenciais_erradas():
    with pytest.raises(RuntimeError):
        odoo_cliente.conectar(ODOO_URL, ODOO_DB, 'usuario_invalido_xyz', 'senha_invalida_xyz')


def test_resolver_coletor_existente(cliente):
    info = odoo_cliente.resolver_coletor(cliente, 'COL-01')
    assert info['site_code'] == 'CMEOX-01'
    assert info['id'] > 0
    assert info['hub_id'] > 0
    assert info['site_id'] > 0


def test_resolver_coletor_inexistente_levanta_erro(cliente):
    with pytest.raises(ValueError):
        odoo_cliente.resolver_coletor(cliente, 'COL-NAO-EXISTE-XYZ')
```

- [ ] **Step 3: Rodar os testes e confirmar que falham**

Run: `python3 -m pytest ingestao/tests/test_odoo_cliente.py -v` (a partir da raiz do repo)
Expected: `ModuleNotFoundError: No module named 'ingestao.odoo_cliente'`.

- [ ] **Step 4: Implementar `ingestao/odoo_cliente.py`**

```python
import xmlrpc.client


class ClienteOdoo:
    def __init__(self, url, db, usuario, senha, uid, models):
        self.url = url
        self.db = db
        self.senha = senha
        self.uid = uid
        self.models = models


def conectar(url, db, usuario, senha):
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, usuario, senha, {})
    if not uid:
        raise RuntimeError(f"autenticação falhou para usuário '{usuario}' no banco '{db}'")
    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
    return ClienteOdoo(url, db, usuario, senha, uid, models)


def executar(cliente, model, metodo, *args, **kwargs):
    return cliente.models.execute_kw(
        cliente.db, cliente.uid, cliente.senha, model, metodo, list(args), kwargs,
    )


def resolver_coletor(cliente, coletor_code):
    coletores = executar(
        cliente, 'sensor_monitor.coletor', 'search_read',
        [('coletor_code', '=', coletor_code)], fields=['id', 'hub_id'],
    )
    if not coletores:
        raise ValueError(f"coletor '{coletor_code}' não encontrado no Odoo")
    coletor = coletores[0]
    hub_id = coletor['hub_id'][0]
    hubs = executar(cliente, 'sensor_monitor.hub', 'read', [hub_id], fields=['site_id'])
    site_id = hubs[0]['site_id'][0]
    sites = executar(cliente, 'sensor_monitor.site', 'read', [site_id], fields=['site_code'])
    return {
        'id': coletor['id'],
        'hub_id': hub_id,
        'site_id': site_id,
        'site_code': sites[0]['site_code'],
    }
```

- [ ] **Step 5: Rodar os testes e confirmar que passam**

Run: `python3 -m pytest ingestao/tests/test_odoo_cliente.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add ingestao/odoo_cliente.py ingestao/tests/test_odoo_cliente.py
git commit -m "feat: cliente XML-RPC do Odoo (conectar, executar, resolver_coletor)"
```

---

## Task 2: Provisionamento do cenário simulado no Odoo

**Files:**
- Create: `ingestao/provisionar_odoo_sim.py`
- Test: `ingestao/tests/test_provisionar_odoo_sim.py`

**Interfaces:**
- Consumes: `odoo_cliente.conectar`, `odoo_cliente.executar`, `odoo_cliente.resolver_coletor` (Task 1).
- Produces: `provisionar(cliente) -> dict` (`{'partner_id', 'site_id', 'hub_id', 'area_id', 'coletor_id'}`, todos ids do Odoo) — idempotente. Constantes públicas: `SITE_CODE`, `HUB_CODE`, `AREA_CODE`, `COLETOR_CODE`, `SENSORES` — usadas pela Task 5's testes.

- [ ] **Step 1: Escrever o teste em `ingestao/tests/test_provisionar_odoo_sim.py`**

```python
from ingestao import odoo_cliente, provisionar_odoo_sim

ODOO_URL = 'http://localhost:8189'
ODOO_DB = 'sentinela'
ODOO_USUARIO = 'admin'
ODOO_SENHA = 'admin'


def _cliente():
    return odoo_cliente.conectar(ODOO_URL, ODOO_DB, ODOO_USUARIO, ODOO_SENHA)


def test_provisionar_e_idempotente():
    cliente = _cliente()
    resultado1 = provisionar_odoo_sim.provisionar(cliente)
    resultado2 = provisionar_odoo_sim.provisionar(cliente)
    assert resultado1 == resultado2


def test_resolver_coletor_apos_provisionar():
    cliente = _cliente()
    provisionar_odoo_sim.provisionar(cliente)
    info = odoo_cliente.resolver_coletor(cliente, provisionar_odoo_sim.COLETOR_CODE)
    assert info['site_code'] == provisionar_odoo_sim.SITE_CODE
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python3 -m pytest ingestao/tests/test_provisionar_odoo_sim.py -v`
Expected: `ModuleNotFoundError: No module named 'ingestao.provisionar_odoo_sim'`.

- [ ] **Step 3: Implementar `ingestao/provisionar_odoo_sim.py`**

```python
import argparse

from . import odoo_cliente

PARTNER_NAME = 'Cliente Simulado'
SITE_CODE = 'SITE-SIM-0001'
HUB_CODE = 'HUB-SIM-0001'
AREA_CODE = 'AREA-SIM-EXPURGO'
COLETOR_CODE = 'COL-SIM-0001'
SENSORES = [
    {'sensor_code': 'SNR-SIM-TEMP-01', 'name': 'Temperatura Simulada', 'measurement_type_code': 'temperatura'},
    {'sensor_code': 'SNR-SIM-PRES-01', 'name': 'Pressão Simulada', 'measurement_type_code': 'pressao_diferencial'},
]


def _buscar_ou_criar(cliente, model, domain, valores):
    encontrados = odoo_cliente.executar(cliente, model, 'search', domain)
    if encontrados:
        return encontrados[0]
    return odoo_cliente.executar(cliente, model, 'create', valores)


def _buscar_id(cliente, model, domain):
    encontrados = odoo_cliente.executar(cliente, model, 'search', domain)
    if not encontrados:
        raise ValueError(f"registro não encontrado em {model} para {domain}")
    return encontrados[0]


def provisionar(cliente):
    partner_id = _buscar_ou_criar(
        cliente, 'res.partner', [('name', '=', PARTNER_NAME)], {'name': PARTNER_NAME},
    )
    site_id = _buscar_ou_criar(
        cliente, 'sensor_monitor.site', [('site_code', '=', SITE_CODE)],
        {'name': 'Site Simulado', 'partner_id': partner_id, 'site_code': SITE_CODE, 'vertical': 'cme_hospitalar'},
    )
    hub_id = _buscar_ou_criar(
        cliente, 'sensor_monitor.hub', [('hub_code', '=', HUB_CODE)],
        {'name': 'Hub Simulado', 'site_id': site_id, 'hub_code': HUB_CODE},
    )
    area_category_id = _buscar_id(cliente, 'sensor_monitor.area.category', [('code', '=', 'EXPURGO')])
    area_id = _buscar_ou_criar(
        cliente, 'sensor_monitor.area', [('area_code', '=', AREA_CODE)],
        {
            'name': 'Expurgo Simulado', 'site_id': site_id,
            'area_category_id': area_category_id, 'area_code': AREA_CODE,
        },
    )
    coletor_id = _buscar_ou_criar(
        cliente, 'sensor_monitor.coletor', [('coletor_code', '=', COLETOR_CODE)],
        {'name': 'Coletor Simulado', 'hub_id': hub_id, 'coletor_code': COLETOR_CODE, 'tipo': 'esp32_wifi'},
    )
    for sensor in SENSORES:
        measurement_type_id = _buscar_id(
            cliente, 'sensor_monitor.measurement.type', [('code', '=', sensor['measurement_type_code'])],
        )
        _buscar_ou_criar(
            cliente, 'sensor_monitor.sensor', [('sensor_code', '=', sensor['sensor_code'])],
            {
                'name': sensor['name'], 'sensor_code': sensor['sensor_code'], 'coletor_id': coletor_id,
                'area_id': area_id, 'measurement_type_id': measurement_type_id, 'protocolo_origem': '4-20mA',
            },
        )
    return {
        'partner_id': partner_id, 'site_id': site_id, 'hub_id': hub_id,
        'area_id': area_id, 'coletor_id': coletor_id,
    }


def main():
    parser = argparse.ArgumentParser(description='Provisiona o cenário simulado no Odoo (idempotente)')
    parser.add_argument('--odoo-url', default='http://localhost:8189', dest='odoo_url')
    parser.add_argument('--odoo-db', default='sentinela', dest='odoo_db')
    parser.add_argument('--odoo-usuario', default='admin', dest='odoo_usuario')
    parser.add_argument('--odoo-senha', default='admin', dest='odoo_senha')
    args = parser.parse_args()
    cliente = odoo_cliente.conectar(args.odoo_url, args.odoo_db, args.odoo_usuario, args.odoo_senha)
    resultado = provisionar(cliente)
    print(f"Provisionado: {resultado}")


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `python3 -m pytest ingestao/tests/test_provisionar_odoo_sim.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add ingestao/provisionar_odoo_sim.py ingestao/tests/test_provisionar_odoo_sim.py
git commit -m "feat: provisionamento idempotente do cenario simulado no Odoo"
```

---

## Task 3: Extensão do `ResultadoValidacao` (`data_referencia`, `hash_final`, `assinatura`)

**Files:**
- Modify: `ingestao/validador.py`
- Modify: `ingestao/tests/test_validador.py`

**Interfaces:**
- Produces: `ResultadoValidacao` ganha 3 campos novos (`data_referencia: str`, `hash_final: str`, `assinatura: str`, todos preenchidos em **todos** os caminhos de retorno de `validar_arquivo`, válido ou não) — usado pela Task 5.

- [ ] **Step 1: Atualizar `ingestao/tests/test_validador.py`** (substitui o arquivo inteiro pelo conteúdo abaixo — mesmos 4 testes, com 3 asserts novos em `test_validar_arquivo_correto` e 1 assert novo em `test_validar_arquivo_com_linha_corrompida`)

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
    assert resultado.data_referencia == '2026-07-18'
    assert resultado.hash_final is not None
    assert resultado.assinatura is not None


def test_validar_arquivo_com_linha_corrompida(tmp_path):
    caminho_arquivo, registro_path = _gerar_arquivo_e_registrar(tmp_path)
    linhas = caminho_arquivo.read_text().split('\n')
    campos = linhas[9].split('|')
    campos[5] = '999.9'
    linhas[9] = '|'.join(campos)
    caminho_arquivo.write_text('\n'.join(linhas))

    resultado = validador.validar_arquivo(caminho_arquivo, registro_path)
    assert resultado.status_validacao == 'invalido'
    assert 'hash' in resultado.motivo_rejeicao.lower()
    assert resultado.leituras == []
    assert resultado.data_referencia == '2026-07-18'


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
Expected: `test_validar_arquivo_correto` falha com `AssertionError` (`resultado.data_referencia` é `AttributeError` — o campo ainda não existe no dataclass atual).

- [ ] **Step 3: Substituir `ingestao/validador.py` inteiro pelo conteúdo abaixo**

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
    data_referencia: str = None
    hash_final: str = None
    assinatura: str = None
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
    data_referencia = metadados_cab.get('data_referencia')
    hash_final_declarado = metadados_rod.get('hash_final')
    assinatura_declarada = metadados_rod.get('assinatura')
    total_linhas = len(linhas_corpo)

    def _invalido(motivo):
        return ResultadoValidacao(
            status_validacao='invalido',
            motivo_rejeicao=motivo,
            total_linhas=total_linhas,
            coletor_id=coletor_id,
            data_referencia=data_referencia,
            hash_final=hash_final_declarado,
            assinatura=assinatura_declarada,
        )

    hash_atual = _hash_seed(cabecalho_canonico)
    leituras = []
    for linha in linhas_corpo:
        parsed = parse_linha_leitura(linha)
        hash_esperado = _hash_linha(hash_atual, parsed['linha_sem_hash'])
        if hash_esperado != parsed['hash']:
            return _invalido(f"cadeia de hash quebrada na linha seq={parsed['seq']}")
        hash_atual = hash_esperado
        leituras.append(parsed)

    if hash_atual != hash_final_declarado:
        return _invalido('hash_final do rodapé não bate com a cadeia recalculada')

    try:
        chave_publica = registro_coletores.obter_chave_publica(registro_path, coletor_id)
    except KeyError as exc:
        return _invalido(str(exc))

    assinatura = base64.b64decode(assinatura_declarada)
    try:
        chave_publica.verify(assinatura, hash_final_declarado.encode(), ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return _invalido('assinatura inválida')

    return ResultadoValidacao(
        status_validacao='valido',
        motivo_rejeicao=None,
        total_linhas=total_linhas,
        coletor_id=coletor_id,
        data_referencia=data_referencia,
        hash_final=hash_final_declarado,
        assinatura=assinatura_declarada,
        leituras=leituras,
    )
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `python3 -m pytest ingestao/tests/test_validador.py -v`
Expected: 4 passed.

- [ ] **Step 5: Rodar a suíte inteira de `ingestao` pra garantir que nada mais quebrou** (o `_invalido` helper mudou a estrutura interna de `validar_arquivo`, ainda que o comportamento externo não tenha mudado nos caminhos já testados)

Run: `python3 -m pytest ingestao/tests/ -v`
Expected: todos os testes até aqui (Tasks 1–3) passam — 4 (odoo_cliente) + 2 (provisionar) + 4 (validador) + 5 (registro_coletores) + 2 (timescale) + 2 (ingestor, ainda com a assinatura antiga de `site_id` — só será atualizado na Task 5) = 19 passed.

- [ ] **Step 6: Commit**

```bash
git add ingestao/validador.py ingestao/tests/test_validador.py
git commit -m "feat: expande ResultadoValidacao com data_referencia, hash_final e assinatura"
```

---

## Task 4: Gravação do `file.ledger` (`escrever_ledger`)

**Files:**
- Modify: `ingestao/odoo_cliente.py`
- Modify: `ingestao/tests/test_odoo_cliente.py`

**Interfaces:**
- Consumes: `provisionar_odoo_sim.provisionar`, `provisionar_odoo_sim.COLETOR_CODE` (Task 2, só em teste).
- Produces: `escrever_ledger(cliente, coletor_odoo_id, tipo_arquivo, data_referencia, status_validacao, motivo_rejeicao, total_linhas, hash_final, assinatura) -> int` (id do registro `sensor_monitor.file.ledger` criado ou atualizado) — usado pela Task 5.

- [ ] **Step 1: Adicionar o teste a `ingestao/tests/test_odoo_cliente.py`** (acrescentar ao final do arquivo, após os 4 testes já existentes)

```python
from ingestao import provisionar_odoo_sim


def test_escrever_ledger_cria_e_atualiza(cliente):
    provisionar_odoo_sim.provisionar(cliente)
    info = odoo_cliente.resolver_coletor(cliente, provisionar_odoo_sim.COLETOR_CODE)
    data_ref = '2020-01-01'  # data de teste, isolada de qualquer arquivo real gerado

    id1 = odoo_cliente.escrever_ledger(
        cliente, info['id'], 'leituras', data_ref, 'valido', None, 2880, 'hash-teste-1', 'assinatura-teste-1',
    )
    try:
        id2 = odoo_cliente.escrever_ledger(
            cliente, info['id'], 'leituras', data_ref, 'valido', None, 2880, 'hash-teste-2', 'assinatura-teste-2',
        )
        assert id1 == id2

        registros = odoo_cliente.executar(
            cliente, 'sensor_monitor.file.ledger', 'read', [id1], fields=['hash_final', 'status_validacao'],
        )
        assert registros[0]['hash_final'] == 'hash-teste-2'
        assert registros[0]['status_validacao'] == 'valido'
    finally:
        odoo_cliente.executar(cliente, 'sensor_monitor.file.ledger', 'unlink', [id1])
```

(A linha `from ingestao import provisionar_odoo_sim` deve ficar junto com os outros imports no topo do arquivo, não no meio — ajuste a posição ao editar.)

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python3 -m pytest ingestao/tests/test_odoo_cliente.py -v`
Expected: `test_escrever_ledger_cria_e_atualiza` falha com `AttributeError: module 'ingestao.odoo_cliente' has no attribute 'escrever_ledger'`.

- [ ] **Step 3: Adicionar `escrever_ledger` ao final de `ingestao/odoo_cliente.py`**

```python
from datetime import datetime


def escrever_ledger(cliente, coletor_odoo_id, tipo_arquivo, data_referencia, status_validacao,
                     motivo_rejeicao, total_linhas, hash_final, assinatura):
    existentes = executar(
        cliente, 'sensor_monitor.file.ledger', 'search',
        [
            ('coletor_id', '=', coletor_odoo_id),
            ('data_referencia', '=', data_referencia),
            ('tipo_arquivo', '=', tipo_arquivo),
        ],
    )
    valores = {
        'coletor_id': coletor_odoo_id,
        'tipo_arquivo': tipo_arquivo,
        'data_referencia': data_referencia,
        'status_validacao': status_validacao,
        'motivo_rejeicao': motivo_rejeicao or False,
        'total_linhas': total_linhas,
        'hash_final': hash_final or False,
        'assinatura': assinatura or False,
        'horario_recebimento': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    if existentes:
        executar(cliente, 'sensor_monitor.file.ledger', 'write', existentes, valores)
        return existentes[0]
    return executar(cliente, 'sensor_monitor.file.ledger', 'create', valores)
```

(Mova o `from datetime import datetime` para o topo do arquivo, junto com `import xmlrpc.client`, em vez de deixar no meio do arquivo.)

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `python3 -m pytest ingestao/tests/test_odoo_cliente.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add ingestao/odoo_cliente.py ingestao/tests/test_odoo_cliente.py
git commit -m "feat: escrever_ledger (cria ou atualiza sensor_monitor.file.ledger)"
```

---

## Task 5: Wire — `ingestor.py` troca `site_id` fixo por resolução via Odoo + grava ledger

**Files:**
- Modify: `ingestao/ingestor.py`
- Modify: `ingestao/tests/test_ingestor.py`

**Interfaces:**
- Consumes: `odoo_cliente.conectar`, `odoo_cliente.resolver_coletor`, `odoo_cliente.escrever_ledger` (Tasks 1, 4); `validador.validar_arquivo` (com os 3 campos novos, Task 3); `timescale.conectar`, `timescale.inserir_leituras` (rodada anterior).
- Produces: `ingerir_arquivo(caminho, registro_path, dsn, cliente_odoo) -> ResultadoIngestao` — **assinatura muda**: `site_id` sai, `cliente_odoo` (já conectado) entra. CLI ganha `--odoo-url`, `--odoo-db`, `--odoo-usuario`, `--odoo-senha`; perde `--site-id`.

- [ ] **Step 1: Substituir `ingestao/tests/test_ingestor.py` inteiro pelo conteúdo abaixo**

```python
from datetime import date

from coletor_simulado import gerador as gerador_simulado
from ingestao import ingestor, odoo_cliente, provisionar_odoo_sim, registro_coletores, timescale

DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'
ODOO_URL = 'http://localhost:8189'
ODOO_DB = 'sentinela'
ODOO_USUARIO = 'admin'
ODOO_SENHA = 'admin'


def _cliente_odoo():
    return odoo_cliente.conectar(ODOO_URL, ODOO_DB, ODOO_USUARIO, ODOO_SENHA)


def _limpar_timescale(site_id):
    conn = timescale.conectar(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sensor_reading WHERE site_id = %s", (site_id,))
        conn.commit()
    finally:
        conn.close()


def _limpar_ledger(cliente, coletor_id, data_referencia):
    registros = odoo_cliente.executar(
        cliente, 'sensor_monitor.file.ledger', 'search',
        [
            ('coletor_id', '=', coletor_id),
            ('data_referencia', '=', data_referencia),
            ('tipo_arquivo', '=', 'leituras'),
        ],
    )
    if registros:
        odoo_cliente.executar(cliente, 'sensor_monitor.file.ledger', 'unlink', registros)


def test_ingerir_arquivo_valido_resolve_site_e_grava_ledger(tmp_path):
    cliente = _cliente_odoo()
    provisionar_odoo_sim.provisionar(cliente)
    info_coletor = odoo_cliente.resolver_coletor(cliente, provisionar_odoo_sim.COLETOR_CODE)
    data = date(2026, 7, 21)

    chave_path = tmp_path / 'chave.pem'
    output_dir = gerador_simulado.gerar_dia(data, tmp_path / 'output', chave_path=chave_path)
    registro_path = tmp_path / 'registro.json'
    registro_coletores.registrar_a_partir_de_chave_privada(registro_path, chave_path, gerador_simulado.COLETOR_ID)
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_leituras_{data.isoformat()}.txt"

    _limpar_timescale(info_coletor['site_code'])
    _limpar_ledger(cliente, info_coletor['id'], data.isoformat())
    try:
        resultado = ingestor.ingerir_arquivo(caminho_arquivo, registro_path, DSN, cliente)
        assert resultado.status_validacao == 'valido'
        assert resultado.total_linhas == 2880
        assert resultado.total_gravado == 2880

        ledgers = odoo_cliente.executar(
            cliente, 'sensor_monitor.file.ledger', 'search_read',
            [
                ('coletor_id', '=', info_coletor['id']),
                ('data_referencia', '=', data.isoformat()),
                ('tipo_arquivo', '=', 'leituras'),
            ],
            fields=['status_validacao', 'total_linhas', 'hash_final'],
        )
        assert len(ledgers) == 1
        assert ledgers[0]['status_validacao'] == 'valido'
        assert ledgers[0]['total_linhas'] == 2880
    finally:
        _limpar_timescale(info_coletor['site_code'])
        _limpar_ledger(cliente, info_coletor['id'], data.isoformat())


def test_ingerir_arquivo_corrompido_grava_ledger_invalido_sem_dados(tmp_path):
    cliente = _cliente_odoo()
    provisionar_odoo_sim.provisionar(cliente)
    info_coletor = odoo_cliente.resolver_coletor(cliente, provisionar_odoo_sim.COLETOR_CODE)
    data = date(2026, 7, 22)

    chave_path = tmp_path / 'chave.pem'
    output_dir = gerador_simulado.gerar_dia(data, tmp_path / 'output', chave_path=chave_path)
    registro_path = tmp_path / 'registro.json'
    registro_coletores.registrar_a_partir_de_chave_privada(registro_path, chave_path, gerador_simulado.COLETOR_ID)
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_leituras_{data.isoformat()}.txt"
    linhas = caminho_arquivo.read_text().split('\n')
    campos = linhas[9].split('|')
    campos[5] = '999.9'
    linhas[9] = '|'.join(campos)
    caminho_arquivo.write_text('\n'.join(linhas))

    _limpar_timescale(info_coletor['site_code'])
    _limpar_ledger(cliente, info_coletor['id'], data.isoformat())
    try:
        resultado = ingestor.ingerir_arquivo(caminho_arquivo, registro_path, DSN, cliente)
        assert resultado.status_validacao == 'invalido'
        assert resultado.total_gravado == 0

        conn = timescale.conectar(DSN)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM sensor_reading WHERE site_id = %s", (info_coletor['site_code'],))
                (total,) = cur.fetchone()
            assert total == 0
        finally:
            conn.close()

        ledgers = odoo_cliente.executar(
            cliente, 'sensor_monitor.file.ledger', 'search_read',
            [
                ('coletor_id', '=', info_coletor['id']),
                ('data_referencia', '=', data.isoformat()),
                ('tipo_arquivo', '=', 'leituras'),
            ],
            fields=['status_validacao'],
        )
        assert len(ledgers) == 1
        assert ledgers[0]['status_validacao'] == 'invalido'
    finally:
        _limpar_timescale(info_coletor['site_code'])
        _limpar_ledger(cliente, info_coletor['id'], data.isoformat())
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python3 -m pytest ingestao/tests/test_ingestor.py -v`
Expected: falha — `ingerir_arquivo()` ainda espera `site_id` como 4º argumento posicional, não `cliente_odoo` (`TypeError` ou comportamento incorreto, já que um objeto `ClienteOdoo` seria tratado como string de `site_id`).

- [ ] **Step 3: Substituir `ingestao/ingestor.py` inteiro pelo conteúdo abaixo**

```python
import argparse
from dataclasses import dataclass

from . import odoo_cliente, timescale, validador


@dataclass
class ResultadoIngestao:
    status_validacao: str
    motivo_rejeicao: str
    total_linhas: int
    total_gravado: int


def ingerir_arquivo(caminho, registro_path, dsn, cliente_odoo):
    resultado_validacao = validador.validar_arquivo(caminho, registro_path)

    try:
        info_coletor = odoo_cliente.resolver_coletor(cliente_odoo, resultado_validacao.coletor_id)
    except ValueError as exc:
        return ResultadoIngestao(
            status_validacao='invalido',
            motivo_rejeicao=str(exc),
            total_linhas=resultado_validacao.total_linhas,
            total_gravado=0,
        )

    total_gravado = 0
    if resultado_validacao.status_validacao == 'valido':
        conn = timescale.conectar(dsn)
        try:
            total_gravado = timescale.inserir_leituras(
                conn, info_coletor['site_code'], resultado_validacao.coletor_id, resultado_validacao.leituras,
            )
        finally:
            conn.close()

    odoo_cliente.escrever_ledger(
        cliente_odoo, info_coletor['id'], 'leituras', resultado_validacao.data_referencia,
        resultado_validacao.status_validacao, resultado_validacao.motivo_rejeicao,
        resultado_validacao.total_linhas, resultado_validacao.hash_final, resultado_validacao.assinatura,
    )

    return ResultadoIngestao(
        status_validacao=resultado_validacao.status_validacao,
        motivo_rejeicao=resultado_validacao.motivo_rejeicao,
        total_linhas=resultado_validacao.total_linhas,
        total_gravado=total_gravado,
    )


def main():
    parser = argparse.ArgumentParser(description='Ingestão de arquivo de leituras do coletor simulado')
    parser.add_argument('--arquivo', required=True)
    parser.add_argument('--registro', default='ingestao/coletores_conhecidos.json')
    parser.add_argument('--dsn', default='postgresql://sentinela:sentinela@localhost:5433/sentinela')
    parser.add_argument('--odoo-url', default='http://localhost:8189', dest='odoo_url')
    parser.add_argument('--odoo-db', default='sentinela', dest='odoo_db')
    parser.add_argument('--odoo-usuario', default='admin', dest='odoo_usuario')
    parser.add_argument('--odoo-senha', default='admin', dest='odoo_senha')
    args = parser.parse_args()
    cliente_odoo = odoo_cliente.conectar(args.odoo_url, args.odoo_db, args.odoo_usuario, args.odoo_senha)
    resultado = ingerir_arquivo(args.arquivo, args.registro, args.dsn, cliente_odoo)
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
git commit -m "feat: ingestor resolve site via Odoo e grava file.ledger (remove site_id fixo)"
```

---

## Task 6: Verificação final (suíte completa + fluxo real ponta a ponta)

**Files:**
- Modify: nenhum arquivo novo — task de verificação/fechamento.

**Interfaces:**
- Consumes: tudo das Tasks 1–5, mais `coletor_simulado/` e `ingestao/timescale.py` das rodadas anteriores.

- [ ] **Step 1: Rodar a suíte combinada completa**

Run (a partir da raiz do repo, com Odoo em `http://localhost:8189` e TimescaleDB em `localhost:5433` já rodando):
```bash
python3 -m pytest coletor_simulado/tests/ ingestao/tests/ -v
```
Expected: 14 (coletor_simulado) + 20 (ingestao: 5 registro + 4 validador + 2 timescale + 5 odoo_cliente + 2 provisionar + 2 ingestor) = **34 passed**, 0 failed.

- [ ] **Step 2: Fluxo real ponta a ponta — provisionar, gerar arquivo, registrar, ingerir**

Run:
```bash
python3 -m ingestao.provisionar_odoo_sim
python3 -m coletor_simulado.gerador --data 2026-07-23 --output-dir coletor_simulado/output
python3 -m ingestao.registro_coletores --registrar COL-SIM-0001 --a-partir-de coletor_simulado/identidade/coletor_privkey.pem --registro ingestao/coletores_conhecidos.json
python3 -m ingestao.ingestor --arquivo coletor_simulado/output/COL-SIM-0001_leituras_2026-07-23.txt --registro ingestao/coletores_conhecidos.json
```
Expected: última linha imprime `status=valido total_linhas=2880 total_gravado=2880 motivo=None`. Note que **não há mais `--site-id`** no comando (resolvido automaticamente via Odoo).

- [ ] **Step 3: Confirmar o `file.ledger` criado no Odoo**

Run:
```bash
python3 -c "
from ingestao import odoo_cliente
cliente = odoo_cliente.conectar('http://localhost:8189', 'sentinela', 'admin', 'admin')
ledgers = odoo_cliente.executar(
    cliente, 'sensor_monitor.file.ledger', 'search_read',
    [('data_referencia', '=', '2026-07-23'), ('tipo_arquivo', '=', 'leituras')],
    fields=['coletor_id', 'status_validacao', 'total_linhas', 'hash_final'],
)
print(ledgers)
"
```
Expected: uma linha, `status_validacao: 'valido'`, `total_linhas: 2880`, `coletor_id` apontando para "Coletor Simulado".

- [ ] **Step 4: Confirmar as leituras no TimescaleDB**

Run:
```bash
docker compose exec timescaledb psql -U sentinela -d sentinela -c "SELECT count(*) FROM sensor_reading WHERE site_id = 'SITE-SIM-0001';"
```
Expected: `count = 2880`.

- [ ] **Step 5: Limpar os dados de verificação (Timescale e o ledger do Step 2/3 — não são fixture automatizada)**

Run:
```bash
docker compose exec timescaledb psql -U sentinela -d sentinela -c "DELETE FROM sensor_reading WHERE site_id = 'SITE-SIM-0001';"
python3 -c "
from ingestao import odoo_cliente
cliente = odoo_cliente.conectar('http://localhost:8189', 'sentinela', 'admin', 'admin')
registros = odoo_cliente.executar(
    cliente, 'sensor_monitor.file.ledger', 'search',
    [('data_referencia', '=', '2026-07-23'), ('tipo_arquivo', '=', 'leituras')],
)
odoo_cliente.executar(cliente, 'sensor_monitor.file.ledger', 'unlink', registros)
print('ledger removido:', registros)
"
```
Expected: `DELETE 2880` e `ledger removido: [<id>]`. **Não remover** o site/hub/coletor/sensores provisionados (`SITE-SIM-0001` etc.) — ficam como fixture permanente para rodadas futuras.

- [ ] **Step 6: Commit final (se houver qualquer ajuste feito durante a verificação)**

```bash
git add -A
git commit -m "chore: verificacao final da integracao Odoo (site + file.ledger)" --allow-empty
```
