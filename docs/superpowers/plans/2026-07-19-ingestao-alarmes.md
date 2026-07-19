# Arquivo de Alarmes + alarm.event Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O serviço de ingestão passa a processar o arquivo `tipo_arquivo=alarmes` (corrige um bug de parsing que quebra para corpo vazio) e cria/atualiza `sensor_monitor.alarm.event` no Odoo a partir das transições `entrada_alarme`/`saida_alarme`. Fecha a Fase 2 do roadmap.

**Architecture:** `validador.py` ganha um parser de linha alternativo e despacha por `tipo_arquivo`; `odoo_cliente.py` ganha `resolver_sensor` + `processar_entrada_alarme`/`processar_saida_alarme`; `ingestor.py` passa a rotear para Timescale (leituras) ou Odoo (alarmes) conforme o tipo do arquivo.

**Tech Stack:** Mesmo da rodada anterior — Python 3 stdlib, `cryptography`, `psycopg2`, `xmlrpc.client`, Odoo 18 e TimescaleDB já rodando.

## Global Constraints

- Timestamps do arquivo (`...T02:00:00-03:00`) devem ser convertidos para **UTC** antes de gravar em qualquer campo `Datetime` do Odoo — usar `datetime.fromisoformat(...).astimezone(timezone.utc)`, nunca fatiar a string ignorando o offset (mesma classe de bug corrigida em `horario_recebimento` na rodada anterior).
- `saida_alarme` sem `entrada_alarme` aberta correspondente (mesmo sensor, `timestamp_resolucao_sensor` vazio): **não cria nada**, conta como órfã (`eventos_orfaos`), não interrompe o processamento dos demais eventos do arquivo.
- `status` do `alarm.event` (workflow humano) nunca é alterado pelo processamento automático de `saida_alarme` — só `timestamp_resolucao_sensor` é escrito.
- `file.ledger` gravado para `alarmes` do mesmo jeito que para `leituras` (mesma função `escrever_ledger`, já genérica).
- Sem reconciliação retroativa de lacunas nesta rodada.

---

## Task 1: Corrige parsing de cabeçalho/rodapé + suporta linha de alarme em `validador.py`

**Files:**
- Modify: `ingestao/validador.py` (substituir arquivo inteiro)
- Modify: `ingestao/tests/test_validador.py` (substituir arquivo inteiro)

**Interfaces:**
- Produces: `parse_linha_alarme(linha) -> dict` (novo); `ResultadoValidacao` ganha `tipo_arquivo: str` e `eventos: list`; `validar_arquivo` despacha por `tipo_arquivo` do cabeçalho — usado pelas Tasks 2 e 3.

- [ ] **Step 1: Substituir `ingestao/tests/test_validador.py` inteiro pelo conteúdo abaixo**

```python
from datetime import date

from coletor_simulado import gerador as gerador_simulado
from coletor_simulado import identidade as identidade_simulado
from ingestao import registro_coletores, validador


def _gerar_dia_e_registrar(tmp_path, data=date(2026, 7, 18), injetar_alarme=False):
    chave_path = tmp_path / 'chave_coletor.pem'
    output_dir = gerador_simulado.gerar_dia(
        data, tmp_path / 'output', injetar_alarme=injetar_alarme, chave_path=chave_path,
    )
    registro_path = tmp_path / 'registro.json'
    registro_coletores.registrar_a_partir_de_chave_privada(registro_path, chave_path, gerador_simulado.COLETOR_ID)
    return output_dir, registro_path


def test_validar_arquivo_correto(tmp_path):
    output_dir, registro_path = _gerar_dia_e_registrar(tmp_path)
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_leituras_2026-07-18.txt"
    resultado = validador.validar_arquivo(caminho_arquivo, registro_path)
    assert resultado.status_validacao == 'valido'
    assert resultado.total_linhas == 2880
    assert len(resultado.leituras) == 2880
    assert resultado.coletor_id == gerador_simulado.COLETOR_ID
    assert resultado.motivo_rejeicao is None
    assert resultado.data_referencia == '2026-07-18'
    assert resultado.hash_final is not None
    assert resultado.assinatura is not None
    assert resultado.tipo_arquivo == 'leituras'


def test_validar_arquivo_com_linha_corrompida(tmp_path):
    output_dir, registro_path = _gerar_dia_e_registrar(tmp_path)
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_leituras_2026-07-18.txt"
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
    output_dir, registro_path = _gerar_dia_e_registrar(tmp_path)
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_leituras_2026-07-18.txt"
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


def test_validar_arquivo_alarme_sem_eventos(tmp_path):
    output_dir, registro_path = _gerar_dia_e_registrar(tmp_path, injetar_alarme=False)
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_alarmes_2026-07-18.txt"
    resultado = validador.validar_arquivo(caminho_arquivo, registro_path)
    assert resultado.status_validacao == 'valido'
    assert resultado.tipo_arquivo == 'alarmes'
    assert resultado.total_linhas == 0
    assert resultado.eventos == []


def test_validar_arquivo_alarme_com_par_entrada_saida(tmp_path):
    output_dir, registro_path = _gerar_dia_e_registrar(tmp_path, injetar_alarme=True)
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_alarmes_2026-07-18.txt"
    resultado = validador.validar_arquivo(caminho_arquivo, registro_path)
    assert resultado.status_validacao == 'valido'
    assert resultado.tipo_arquivo == 'alarmes'
    assert len(resultado.eventos) == 2
    assert resultado.eventos[0]['tipo_evento'] == 'entrada_alarme'
    assert resultado.eventos[1]['tipo_evento'] == 'saida_alarme'
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python3 -m pytest ingestao/tests/test_validador.py -v` (a partir da raiz do repo)
Expected: os 4 primeiros testes falham com `TypeError` (chamada com `injetar_alarme=` num `gerar_dia` que já aceita, então na verdade devem passar — mas os 2 últimos falham com `AttributeError: 'ResultadoValidacao' object has no attribute 'tipo_arquivo'` ou `eventos`).

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

HEADER_KEYS = {
    'schema_version', 'tipo_arquivo', 'coletor_id', 'hub_id',
    'coletor_pubkey_fingerprint', 'data_referencia', 'timezone_offset',
    'firmware_version', 'dia_anterior_hash_final',
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


def parse_linha_alarme(linha):
    campos = linha.split('|')
    (seq, timestamp, sensor_id, area_id, tipo_medida, tipo_evento, tipo_violacao,
     valor, limite_min_vigente, limite_max_vigente, hash_linha) = campos
    linha_sem_hash = '|'.join(campos[:-1])
    return {
        'seq': int(seq),
        'timestamp': timestamp,
        'sensor_id': sensor_id,
        'area_id': area_id,
        'tipo_medida': tipo_medida,
        'tipo_evento': tipo_evento,
        'tipo_violacao': tipo_violacao,
        'valor': float(valor),
        'limite_min_vigente': None if limite_min_vigente == '—' else float(limite_min_vigente),
        'limite_max_vigente': None if limite_max_vigente == '—' else float(limite_max_vigente),
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
    tipo_arquivo = metadados_cab.get('tipo_arquivo')
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
            tipo_arquivo=tipo_arquivo,
        )

    parse_linha = parse_linha_alarme if tipo_arquivo == 'alarmes' else parse_linha_leitura

    hash_atual = _hash_seed(cabecalho_canonico)
    linhas_parseadas = []
    for linha in linhas_corpo:
        parsed = parse_linha(linha)
        hash_esperado = _hash_linha(hash_atual, parsed['linha_sem_hash'])
        if hash_esperado != parsed['hash']:
            return _invalido(f"cadeia de hash quebrada na linha seq={parsed['seq']}")
        hash_atual = hash_esperado
        linhas_parseadas.append(parsed)

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

    resultado = ResultadoValidacao(
        status_validacao='valido',
        motivo_rejeicao=None,
        total_linhas=total_linhas,
        coletor_id=coletor_id,
        data_referencia=data_referencia,
        hash_final=hash_final_declarado,
        assinatura=assinatura_declarada,
        tipo_arquivo=tipo_arquivo,
    )
    if tipo_arquivo == 'alarmes':
        resultado.eventos = linhas_parseadas
    else:
        resultado.leituras = linhas_parseadas
    return resultado
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `python3 -m pytest ingestao/tests/test_validador.py -v`
Expected: 6 passed.

- [ ] **Step 5: Rodar a suíte inteira de `ingestao` pra garantir que nada mais quebrou**

Run: `python3 -m pytest ingestao/tests/ -v`
Expected: todos os testes existentes continuam passando (21 anteriores − 4 substituídos + 6 novos = 23 passed).

- [ ] **Step 6: Commit**

```bash
git add ingestao/validador.py ingestao/tests/test_validador.py
git commit -m "fix: parsing de cabecalho por chave conhecida (corrige alarme sem eventos) + suporte a linha de alarme"
```

---

## Task 2: Resolução de sensor + processamento de evento de alarme (`odoo_cliente.py`)

**Files:**
- Modify: `ingestao/odoo_cliente.py`
- Modify: `ingestao/tests/test_odoo_cliente.py`

**Interfaces:**
- Consumes: `provisionar_odoo_sim.provisionar`, `provisionar_odoo_sim.COLETOR_CODE` (só em teste).
- Produces: `resolver_sensor(cliente, sensor_code) -> dict` (`{'id', 'area_id'}`, levanta `ValueError`); `processar_entrada_alarme(cliente, evento, sensor_odoo_id, area_odoo_id, coletor_odoo_id, hash_arquivo) -> int`; `processar_saida_alarme(cliente, evento, sensor_odoo_id) -> int | None` — usados pela Task 3.

- [ ] **Step 1: Adicionar os testes ao final de `ingestao/tests/test_odoo_cliente.py`**

```python
def test_resolver_sensor_existente(cliente):
    provisionar_odoo_sim.provisionar(cliente)
    info = odoo_cliente.resolver_sensor(cliente, 'SNR-SIM-TEMP-01')
    assert info['id'] > 0
    assert info['area_id'] > 0


def test_resolver_sensor_inexistente_levanta_erro(cliente):
    with pytest.raises(ValueError):
        odoo_cliente.resolver_sensor(cliente, 'SNR-NAO-EXISTE-XYZ')


def test_processar_entrada_e_saida_alarme(cliente):
    provisionar_odoo_sim.provisionar(cliente)
    info_sensor = odoo_cliente.resolver_sensor(cliente, 'SNR-SIM-PRES-01')
    info_coletor = odoo_cliente.resolver_coletor(cliente, provisionar_odoo_sim.COLETOR_CODE)

    evento_entrada = {
        'timestamp': '2020-02-02T02:00:00-03:00', 'valor': 1.0,
        'tipo_violacao': 'acima_limite', 'limite_min_vigente': None, 'limite_max_vigente': -2.5,
    }
    evento_id = odoo_cliente.processar_entrada_alarme(
        cliente, evento_entrada, info_sensor['id'], info_sensor['area_id'], info_coletor['id'], 'hash-teste',
    )
    try:
        registros = odoo_cliente.executar(
            cliente, 'sensor_monitor.alarm.event', 'read', [evento_id],
            fields=['status', 'timestamp_resolucao_sensor', 'limite_configurado_snapshot'],
        )
        assert registros[0]['status'] == 'aberto'
        assert registros[0]['timestamp_resolucao_sensor'] is False
        assert registros[0]['limite_configurado_snapshot'] == -2.5

        evento_saida = {'timestamp': '2020-02-02T02:07:00-03:00'}
        resolvido_id = odoo_cliente.processar_saida_alarme(cliente, evento_saida, info_sensor['id'])
        assert resolvido_id == evento_id

        registros = odoo_cliente.executar(
            cliente, 'sensor_monitor.alarm.event', 'read', [evento_id], fields=['timestamp_resolucao_sensor'],
        )
        assert registros[0]['timestamp_resolucao_sensor'] is not False
    finally:
        odoo_cliente.executar(cliente, 'sensor_monitor.alarm.event', 'unlink', [evento_id])


def test_processar_saida_alarme_sem_entrada_aberta_retorna_none(cliente):
    provisionar_odoo_sim.provisionar(cliente)
    info_sensor = odoo_cliente.resolver_sensor(cliente, 'SNR-SIM-TEMP-01')
    evento_saida = {'timestamp': '2020-03-03T03:00:00-03:00'}
    resultado = odoo_cliente.processar_saida_alarme(cliente, evento_saida, info_sensor['id'])
    assert resultado is None
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python3 -m pytest ingestao/tests/test_odoo_cliente.py -v` (a partir da raiz do repo)
Expected: `AttributeError: module 'ingestao.odoo_cliente' has no attribute 'resolver_sensor'`.

- [ ] **Step 3: Atualizar o import no topo de `ingestao/odoo_cliente.py`** — trocar

```python
import xmlrpc.client
from datetime import datetime
```

por

```python
import xmlrpc.client
from datetime import datetime, timezone
```

- [ ] **Step 4: Adicionar ao final de `ingestao/odoo_cliente.py`**

```python
def _timestamp_arquivo_para_utc(timestamp_iso):
    dt = datetime.fromisoformat(timestamp_iso)
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def resolver_sensor(cliente, sensor_code):
    sensores = executar(
        cliente, 'sensor_monitor.sensor', 'search_read',
        [('sensor_code', '=', sensor_code)], fields=['id', 'area_id'],
    )
    if not sensores:
        raise ValueError(f"sensor '{sensor_code}' não encontrado no Odoo")
    sensor = sensores[0]
    return {'id': sensor['id'], 'area_id': sensor['area_id'][0]}


def processar_entrada_alarme(cliente, evento, sensor_odoo_id, area_odoo_id, coletor_odoo_id, hash_arquivo):
    if evento['tipo_violacao'] == 'acima_limite':
        limite_snapshot = evento['limite_max_vigente']
    elif evento['tipo_violacao'] == 'abaixo_limite':
        limite_snapshot = evento['limite_min_vigente']
    else:
        limite_snapshot = None
    valores = {
        'sensor_id': sensor_odoo_id,
        'area_id': area_odoo_id,
        'coletor_id': coletor_odoo_id,
        'timestamp_deteccao': _timestamp_arquivo_para_utc(evento['timestamp']),
        'valor_lido': evento['valor'],
        'tipo_violacao': evento['tipo_violacao'],
        'limite_configurado_snapshot': limite_snapshot if limite_snapshot is not None else 0.0,
        'origem_arquivo_hash': hash_arquivo or False,
        'status': 'aberto',
    }
    return executar(cliente, 'sensor_monitor.alarm.event', 'create', valores)


def processar_saida_alarme(cliente, evento, sensor_odoo_id):
    abertos = executar(
        cliente, 'sensor_monitor.alarm.event', 'search',
        [
            ('sensor_id', '=', sensor_odoo_id),
            ('timestamp_resolucao_sensor', '=', False),
        ],
        order='timestamp_deteccao desc', limit=1,
    )
    if not abertos:
        return None
    executar(
        cliente, 'sensor_monitor.alarm.event', 'write', abertos,
        {'timestamp_resolucao_sensor': _timestamp_arquivo_para_utc(evento['timestamp'])},
    )
    return abertos[0]
```

- [ ] **Step 5: Rodar os testes e confirmar que passam**

Run: `python3 -m pytest ingestao/tests/test_odoo_cliente.py -v`
Expected: 9 passed.

- [ ] **Step 6: Commit**

```bash
git add ingestao/odoo_cliente.py ingestao/tests/test_odoo_cliente.py
git commit -m "feat: resolver_sensor e processamento de entrada/saida de alarme (com conversao de timestamp para UTC)"
```

---

## Task 3: Wire — `ingestor.py` roteia por `tipo_arquivo` (Timescale para leituras, alarm.event para alarmes)

**Files:**
- Modify: `ingestao/ingestor.py` (substituir arquivo inteiro)
- Modify: `ingestao/tests/test_ingestor.py` (substituir arquivo inteiro)

**Interfaces:**
- Consumes: `odoo_cliente.resolver_sensor`, `odoo_cliente.processar_entrada_alarme`, `odoo_cliente.processar_saida_alarme` (Task 2); `validador.validar_arquivo` (com `tipo_arquivo`/`eventos`, Task 1).
- Produces: `ResultadoIngestao` ganha `eventos_orfaos: int = 0`. `ingerir_arquivo` mesma assinatura, comportamento roteado por `resultado_validacao.tipo_arquivo`.

- [ ] **Step 1: Substituir `ingestao/tests/test_ingestor.py` inteiro pelo conteúdo abaixo**

```python
from datetime import date

from coletor_simulado import gerador as gerador_simulado
from ingestao import ingestor, odoo_cliente, provisionar_odoo_sim, registro_coletores, timescale, validador

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


def _limpar_ledger(cliente, coletor_id, data_referencia, tipo_arquivo='leituras'):
    registros = odoo_cliente.executar(
        cliente, 'sensor_monitor.file.ledger', 'search',
        [
            ('coletor_id', '=', coletor_id),
            ('data_referencia', '=', data_referencia),
            ('tipo_arquivo', '=', tipo_arquivo),
        ],
    )
    if registros:
        odoo_cliente.executar(cliente, 'sensor_monitor.file.ledger', 'unlink', registros)


def _limpar_alarm_events(cliente, sensor_odoo_id):
    eventos = odoo_cliente.executar(
        cliente, 'sensor_monitor.alarm.event', 'search', [('sensor_id', '=', sensor_odoo_id)],
    )
    if eventos:
        odoo_cliente.executar(cliente, 'sensor_monitor.alarm.event', 'unlink', eventos)


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


def test_ingerir_arquivo_coletor_desconhecido_nao_grava_nada(tmp_path):
    cliente = _cliente_odoo()
    coletor_id_desconhecido = 'COL-INEXISTENTE-XYZ'
    data = date(2026, 7, 23)

    coletor_id_original = gerador_simulado.COLETOR_ID
    gerador_simulado.COLETOR_ID = coletor_id_desconhecido
    try:
        chave_path = tmp_path / 'chave.pem'
        output_dir = gerador_simulado.gerar_dia(data, tmp_path / 'output', chave_path=chave_path)
    finally:
        gerador_simulado.COLETOR_ID = coletor_id_original

    registro_path = tmp_path / 'registro.json'
    registro_coletores.registrar_a_partir_de_chave_privada(registro_path, chave_path, coletor_id_desconhecido)
    caminho_arquivo = output_dir / f"{coletor_id_desconhecido}_leituras_{data.isoformat()}.txt"

    resultado_validacao_local = validador.validar_arquivo(caminho_arquivo, registro_path)
    assert resultado_validacao_local.status_validacao == 'valido'

    resultado = ingestor.ingerir_arquivo(caminho_arquivo, registro_path, DSN, cliente)
    assert resultado.status_validacao == 'invalido'
    assert 'não encontrado' in resultado.motivo_rejeicao
    assert coletor_id_desconhecido in resultado.motivo_rejeicao
    assert resultado.total_gravado == 0


def test_ingerir_arquivo_alarme_sem_eventos_grava_ledger(tmp_path):
    cliente = _cliente_odoo()
    provisionar_odoo_sim.provisionar(cliente)
    info_coletor = odoo_cliente.resolver_coletor(cliente, provisionar_odoo_sim.COLETOR_CODE)
    data = date(2026, 7, 24)

    chave_path = tmp_path / 'chave.pem'
    output_dir = gerador_simulado.gerar_dia(
        data, tmp_path / 'output', injetar_alarme=False, chave_path=chave_path,
    )
    registro_path = tmp_path / 'registro.json'
    registro_coletores.registrar_a_partir_de_chave_privada(registro_path, chave_path, gerador_simulado.COLETOR_ID)
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_alarmes_{data.isoformat()}.txt"

    _limpar_ledger(cliente, info_coletor['id'], data.isoformat(), tipo_arquivo='alarmes')
    try:
        resultado = ingestor.ingerir_arquivo(caminho_arquivo, registro_path, DSN, cliente)
        assert resultado.status_validacao == 'valido'
        assert resultado.total_linhas == 0
        assert resultado.total_gravado == 0
        assert resultado.eventos_orfaos == 0

        ledgers = odoo_cliente.executar(
            cliente, 'sensor_monitor.file.ledger', 'search_read',
            [
                ('coletor_id', '=', info_coletor['id']),
                ('data_referencia', '=', data.isoformat()),
                ('tipo_arquivo', '=', 'alarmes'),
            ],
            fields=['status_validacao', 'total_linhas'],
        )
        assert len(ledgers) == 1
        assert ledgers[0]['status_validacao'] == 'valido'
    finally:
        _limpar_ledger(cliente, info_coletor['id'], data.isoformat(), tipo_arquivo='alarmes')


def test_ingerir_arquivo_alarme_com_par_cria_e_resolve_alarm_event(tmp_path):
    cliente = _cliente_odoo()
    provisionar_odoo_sim.provisionar(cliente)
    info_coletor = odoo_cliente.resolver_coletor(cliente, provisionar_odoo_sim.COLETOR_CODE)
    info_sensor = odoo_cliente.resolver_sensor(cliente, 'SNR-SIM-PRES-01')
    data = date(2026, 7, 25)

    chave_path = tmp_path / 'chave.pem'
    output_dir = gerador_simulado.gerar_dia(
        data, tmp_path / 'output', injetar_alarme=True, chave_path=chave_path,
    )
    registro_path = tmp_path / 'registro.json'
    registro_coletores.registrar_a_partir_de_chave_privada(registro_path, chave_path, gerador_simulado.COLETOR_ID)
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_alarmes_{data.isoformat()}.txt"

    _limpar_ledger(cliente, info_coletor['id'], data.isoformat(), tipo_arquivo='alarmes')
    _limpar_alarm_events(cliente, info_sensor['id'])
    try:
        resultado = ingestor.ingerir_arquivo(caminho_arquivo, registro_path, DSN, cliente)
        assert resultado.status_validacao == 'valido'
        assert resultado.total_linhas == 2
        assert resultado.total_gravado == 2
        assert resultado.eventos_orfaos == 0

        eventos = odoo_cliente.executar(
            cliente, 'sensor_monitor.alarm.event', 'search_read',
            [('sensor_id', '=', info_sensor['id'])],
            fields=['status', 'timestamp_resolucao_sensor'],
        )
        assert len(eventos) == 1
        assert eventos[0]['status'] == 'aberto'
        assert eventos[0]['timestamp_resolucao_sensor'] is not False
    finally:
        _limpar_ledger(cliente, info_coletor['id'], data.isoformat(), tipo_arquivo='alarmes')
        _limpar_alarm_events(cliente, info_sensor['id'])
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python3 -m pytest ingestao/tests/test_ingestor.py -v`
Expected: os 3 primeiros testes continuam passando; os 2 novos de alarme falham (`AttributeError` em `resultado.eventos_orfaos`, ou o ledger de `alarmes` nunca é criado porque `ingerir_arquivo` ainda ignora `tipo_arquivo` e grava sempre como `'leituras'`).

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
    eventos_orfaos: int = 0


def _processar_leituras(dsn, info_coletor, resultado_validacao):
    conn = timescale.conectar(dsn)
    try:
        return timescale.inserir_leituras(
            conn, info_coletor['site_code'], resultado_validacao.coletor_id, resultado_validacao.leituras,
        )
    finally:
        conn.close()


def _processar_alarmes(cliente_odoo, info_coletor, resultado_validacao):
    eventos_orfaos = 0
    for evento in resultado_validacao.eventos:
        info_sensor = odoo_cliente.resolver_sensor(cliente_odoo, evento['sensor_id'])
        if evento['tipo_evento'] == 'entrada_alarme':
            odoo_cliente.processar_entrada_alarme(
                cliente_odoo, evento, info_sensor['id'], info_sensor['area_id'],
                info_coletor['id'], resultado_validacao.hash_final,
            )
        elif evento['tipo_evento'] == 'saida_alarme':
            resolvido = odoo_cliente.processar_saida_alarme(cliente_odoo, evento, info_sensor['id'])
            if resolvido is None:
                eventos_orfaos += 1
    return eventos_orfaos


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
    eventos_orfaos = 0
    if resultado_validacao.status_validacao == 'valido':
        if resultado_validacao.tipo_arquivo == 'alarmes':
            eventos_orfaos = _processar_alarmes(cliente_odoo, info_coletor, resultado_validacao)
            total_gravado = len(resultado_validacao.eventos)
        else:
            total_gravado = _processar_leituras(dsn, info_coletor, resultado_validacao)

    odoo_cliente.escrever_ledger(
        cliente_odoo, info_coletor['id'], resultado_validacao.tipo_arquivo, resultado_validacao.data_referencia,
        resultado_validacao.status_validacao, resultado_validacao.motivo_rejeicao,
        resultado_validacao.total_linhas, resultado_validacao.hash_final, resultado_validacao.assinatura,
    )

    return ResultadoIngestao(
        status_validacao=resultado_validacao.status_validacao,
        motivo_rejeicao=resultado_validacao.motivo_rejeicao,
        total_linhas=resultado_validacao.total_linhas,
        total_gravado=total_gravado,
        eventos_orfaos=eventos_orfaos,
    )


def main():
    parser = argparse.ArgumentParser(description='Ingestão de arquivo (leituras ou alarmes) do coletor simulado')
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
        f"total_gravado={resultado.total_gravado} eventos_orfaos={resultado.eventos_orfaos} "
        f"motivo={resultado.motivo_rejeicao}"
    )


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `python3 -m pytest ingestao/tests/test_ingestor.py -v`
Expected: 5 passed.

- [ ] **Step 5: Rodar a suíte inteira**

Run: `python3 -m pytest coletor_simulado/tests/ ingestao/tests/ -v`
Expected: 14 (coletor_simulado) + 29 (ingestao: 5 registro + 6 validador + 2 timescale + 9 odoo_cliente + 2 provisionar + 5 ingestor) = **43 passed**.

- [ ] **Step 6: Commit**

```bash
git add ingestao/ingestor.py ingestao/tests/test_ingestor.py
git commit -m "feat: ingestor roteia por tipo_arquivo (timescale para leituras, alarm.event para alarmes)"
```

---

## Task 4: Verificação final (suíte completa + fluxo real ponta a ponta com alarme)

**Files:**
- Modify: nenhum arquivo novo — task de verificação/fechamento.

**Interfaces:**
- Consumes: tudo das Tasks 1–3, mais `coletor_simulado/` e o restante de `ingestao/` das rodadas anteriores.

- [ ] **Step 1: Rodar a suíte combinada completa**

Run (a partir da raiz do repo, com Odoo em `http://localhost:8189` e TimescaleDB em `localhost:5433` já rodando):
```bash
python3 -m pytest coletor_simulado/tests/ ingestao/tests/ -v
```
Expected: **43 passed**, 0 failed.

- [ ] **Step 2: Fluxo real ponta a ponta — gerar dia com alarme injetado, ingerir os dois arquivos**

Run:
```bash
python3 -m ingestao.provisionar_odoo_sim
python3 -m coletor_simulado.gerador --data 2026-07-26 --output-dir coletor_simulado/output --injetar-alarme
python3 -m ingestao.registro_coletores --registrar COL-SIM-0001 --a-partir-de coletor_simulado/identidade/coletor_privkey.pem --registro ingestao/coletores_conhecidos.json
python3 -m ingestao.ingestor --arquivo coletor_simulado/output/COL-SIM-0001_leituras_2026-07-26.txt --registro ingestao/coletores_conhecidos.json
python3 -m ingestao.ingestor --arquivo coletor_simulado/output/COL-SIM-0001_alarmes_2026-07-26.txt --registro ingestao/coletores_conhecidos.json
```
Expected: primeira ingestão imprime `status=valido total_linhas=2880 total_gravado=2880 eventos_orfaos=0 motivo=None`; segunda imprime `status=valido total_linhas=2 total_gravado=2 eventos_orfaos=0 motivo=None`.

- [ ] **Step 3: Confirmar o `alarm.event` criado e resolvido no Odoo**

Run:
```bash
python3 -c "
from ingestao import odoo_cliente
cliente = odoo_cliente.conectar('http://localhost:8189', 'sentinela', 'admin', 'admin')
info_sensor = odoo_cliente.resolver_sensor(cliente, 'SNR-SIM-PRES-01')
eventos = odoo_cliente.executar(
    cliente, 'sensor_monitor.alarm.event', 'search_read',
    [('sensor_id', '=', info_sensor['id'])],
    fields=['timestamp_deteccao', 'timestamp_resolucao_sensor', 'status', 'tipo_violacao'],
)
print(eventos)
"
```
Expected: uma linha, `status: 'aberto'`, `timestamp_resolucao_sensor` preenchido (não `False`), `tipo_violacao: 'acima_limite'`.

- [ ] **Step 4: Confirmar os dois `file.ledger` (leituras e alarmes) do dia**

Run:
```bash
python3 -c "
from ingestao import odoo_cliente
cliente = odoo_cliente.conectar('http://localhost:8189', 'sentinela', 'admin', 'admin')
ledgers = odoo_cliente.executar(
    cliente, 'sensor_monitor.file.ledger', 'search_read',
    [('data_referencia', '=', '2026-07-26')],
    fields=['tipo_arquivo', 'status_validacao', 'total_linhas'],
)
print(sorted(ledgers, key=lambda l: l['tipo_arquivo']))
"
```
Expected: 2 registros, `tipo_arquivo` `'alarmes'` (`total_linhas: 2`) e `'leituras'` (`total_linhas: 2880`), ambos `status_validacao: 'valido'`.

- [ ] **Step 5: Limpar os dados de verificação (Timescale, os 2 ledgers e o alarm.event — manter o cadastro provisionado)**

Run:
```bash
docker compose exec timescaledb psql -U sentinela -d sentinela -c "DELETE FROM sensor_reading WHERE site_id = 'SITE-SIM-0001';"
python3 -c "
from ingestao import odoo_cliente
cliente = odoo_cliente.conectar('http://localhost:8189', 'sentinela', 'admin', 'admin')
ledgers = odoo_cliente.executar(
    cliente, 'sensor_monitor.file.ledger', 'search', [('data_referencia', '=', '2026-07-26')],
)
odoo_cliente.executar(cliente, 'sensor_monitor.file.ledger', 'unlink', ledgers)
info_sensor = odoo_cliente.resolver_sensor(cliente, 'SNR-SIM-PRES-01')
eventos = odoo_cliente.executar(
    cliente, 'sensor_monitor.alarm.event', 'search', [('sensor_id', '=', info_sensor['id'])],
)
odoo_cliente.executar(cliente, 'sensor_monitor.alarm.event', 'unlink', eventos)
print('ledgers removidos:', ledgers, '| eventos removidos:', eventos)
"
```
Expected: `DELETE 2880` e a impressão dos ids removidos.

- [ ] **Step 6: Commit final**

```bash
git add -A
git commit -m "chore: verificacao final do arquivo de alarmes + alarm.event (fecha Fase 2)" --allow-empty
```
