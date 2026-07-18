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
