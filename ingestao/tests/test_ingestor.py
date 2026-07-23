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
    idx_primeira_linha_corpo = next(i for i, l in enumerate(linhas) if l and not l.startswith('#'))
    campos = linhas[idx_primeira_linha_corpo].split('|')
    campos[5] = '999.9'
    linhas[idx_primeira_linha_corpo] = '|'.join(campos)
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


def test_ingerir_arquivo_alarme_sensor_desconhecido_grava_ledger_invalido(tmp_path):
    cliente = _cliente_odoo()
    provisionar_odoo_sim.provisionar(cliente)
    info_coletor = odoo_cliente.resolver_coletor(cliente, provisionar_odoo_sim.COLETOR_CODE)
    sensor_code_original = gerador_simulado.SENSORES[1]['sensor_id']
    assert sensor_code_original == 'SNR-SIM-PRES-01'
    info_sensor = odoo_cliente.resolver_sensor(cliente, sensor_code_original)
    data = date(2026, 7, 26)

    chave_path = tmp_path / 'chave.pem'
    output_dir = gerador_simulado.gerar_dia(
        data, tmp_path / 'output', injetar_alarme=True, chave_path=chave_path,
    )
    registro_path = tmp_path / 'registro.json'
    registro_coletores.registrar_a_partir_de_chave_privada(registro_path, chave_path, gerador_simulado.COLETOR_ID)
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_alarmes_{data.isoformat()}.txt"

    sensor_code_temporario = 'SNR-SIM-PRES-01-RENOMEADO-TESTE'
    _limpar_ledger(cliente, info_coletor['id'], data.isoformat(), tipo_arquivo='alarmes')
    odoo_cliente.executar(
        cliente, 'sensor_monitor.sensor', 'write', [info_sensor['id']], {'sensor_code': sensor_code_temporario},
    )
    try:
        resultado = ingestor.ingerir_arquivo(caminho_arquivo, registro_path, DSN, cliente)
        assert resultado.status_validacao == 'invalido'
        assert sensor_code_original in resultado.motivo_rejeicao
        assert resultado.total_gravado == 0

        ledgers = odoo_cliente.executar(
            cliente, 'sensor_monitor.file.ledger', 'search_read',
            [
                ('coletor_id', '=', info_coletor['id']),
                ('data_referencia', '=', data.isoformat()),
                ('tipo_arquivo', '=', 'alarmes'),
            ],
            fields=['status_validacao', 'motivo_rejeicao', 'total_linhas'],
        )
        assert len(ledgers) == 1
        assert ledgers[0]['status_validacao'] == 'invalido'
        assert sensor_code_original in ledgers[0]['motivo_rejeicao']
        assert ledgers[0]['total_linhas'] == 2
    finally:
        odoo_cliente.executar(
            cliente, 'sensor_monitor.sensor', 'write', [info_sensor['id']], {'sensor_code': sensor_code_original},
        )
        restaurado = odoo_cliente.resolver_sensor(cliente, sensor_code_original)
        assert restaurado['id'] == info_sensor['id']
        _limpar_ledger(cliente, info_coletor['id'], data.isoformat(), tipo_arquivo='alarmes')
        _limpar_alarm_events(cliente, info_sensor['id'])


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
    assert r.total_gravado == 0
    # F: rejeição de tenant precisa deixar rastro no ledger (não é early-return silencioso)
    assert 'args' in escritos, "escrever_ledger deve ser chamado mesmo em rejeição de tenant"
    args_ledger = escritos['args']
    assert args_ledger[4] == 'invalido'
    assert 'tenant' in args_ledger[5].lower()


def test_rejeita_por_crypto_nao_e_mascarado_por_tenant_mismatch(monkeypatch):
    """Arquivo com hdr_sig inválida (crypto) não deve virar motivo de tenant,
    mesmo que o cliente_id do header também esteja mutado."""
    from ingestao import ingestor, validador
    res_val = validador.ResultadoValidacao(
        status_validacao='invalido', motivo_rejeicao='hdr_sig inválida', total_linhas=1,
        coletor_id='COL-1', data_referencia='2026-07-16', tipo_arquivo='leituras',
        cliente_id='CLI-INTRUSO', site_id='SITE-1', leituras=[])
    monkeypatch.setattr(validador, 'validar_arquivo', lambda *a, **k: res_val)
    monkeypatch.setattr(ingestor.odoo_cliente, 'resolver_coletor',
                        lambda c, cid: {'id': 1, 'site_code': 'SITE-1', 'cliente_id': 'CLI-1'})
    escritos = {}
    monkeypatch.setattr(ingestor.odoo_cliente, 'escrever_ledger',
                        lambda *a, **k: escritos.setdefault('args', a))
    r = ingestor.ingerir_arquivo('x', 'reg', 'dsn', object())
    assert r.status_validacao == 'invalido'
    assert r.motivo_rejeicao == 'hdr_sig inválida'
    assert 'tenant' not in r.motivo_rejeicao.lower()
    assert 'args' in escritos
    assert escritos['args'][4] == 'invalido'
    assert escritos['args'][5] == 'hdr_sig inválida'
