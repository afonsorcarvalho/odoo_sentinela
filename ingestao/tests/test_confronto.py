from datetime import datetime, timezone

from hub.arquivo_diario import ArquivoDiario
from hub.assinador import AssinadorSoftware
from ingestao import confronto, registro_coletores, timescale

DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'


def _leitura(ts, valor):
    return {'timestamp': ts, 'sensor_id': 'SNR-1', 'area_id': 'EXPURGO',
            'tipo_medida': 'temperatura', 'valor': valor, 'unidade': 'C',
            'protocolo_origem': '4-20ma', 'status_leitura': 'ok',
            'cert_ver': 3, 'cal_ganho': 0.965, 'cal_offset': 0.33}


def _gerar_arquivo(tmp_path, leituras=None):
    # ts SEMPRE tz-aware (UTC aqui) — o writer emite offset e o confronto exige
    # timestamp aware (_ts_utc_iso levanta em naive).
    leituras = leituras or [(datetime(2026, 7, 16, 3, 1, 0, tzinfo=timezone.utc), 96.83)]
    assinador = AssinadorSoftware(str(tmp_path / "k.pem"))
    arq = ArquivoDiario('COL-CONF', 'HUB-1', '2.3.1', '+00:00', str(tmp_path / "d"),
                        assinador, cliente_id='CLI-1', site_id='SITE-1')
    for ts, valor in leituras:
        arq.registrar(_leitura(ts, valor))
    arq.selar('2026-07-16')
    registro = str(tmp_path / "reg.json")
    registro_coletores.registrar_coletor(registro, 'COL-CONF', assinador.chave_publica_pem())
    return arq.caminho('2026-07-16'), registro


def _limpar(conn):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM sensor_reading WHERE coletor_id = 'COL-CONF'")
    conn.commit()


def test_confronto_ok_quando_assinaturas_e_valores_batem(tmp_path):
    caminho, registro = _gerar_arquivo(tmp_path)
    conn = timescale.conectar(DSN)
    try:
        _limpar(conn)
        timescale.inserir_leituras(
            conn, 'SITE-1', 'COL-CONF',
            [{'timestamp': datetime(2026, 7, 16, 3, 1, 0, tzinfo=timezone.utc),
              'sensor_id': 'SNR-1', 'area_id': 'EXPURGO', 'tipo_medida': 'temperatura',
              'valor': 96.83, 'unidade': 'C', 'protocolo_origem': '4-20ma',
              'status_leitura': 'ok'}])
        r = confronto.confrontar_arquivo(str(caminho), registro, conn)
        assert r.assinaturas_ok is True
        assert r.valores_ok is True
        assert r.divergencias == []
    finally:
        _limpar(conn)
        conn.close()


def test_confronto_detecta_valor_adulterado_no_timescale(tmp_path):
    caminho, registro = _gerar_arquivo(tmp_path)
    conn = timescale.conectar(DSN)
    try:
        _limpar(conn)
        timescale.inserir_leituras(
            conn, 'SITE-1', 'COL-CONF',
            [{'timestamp': datetime(2026, 7, 16, 3, 1, 0, tzinfo=timezone.utc),
              'sensor_id': 'SNR-1', 'area_id': 'EXPURGO', 'tipo_medida': 'temperatura',
              'valor': 42.00, 'unidade': 'C', 'protocolo_origem': '4-20ma',  # adulterado!
              'status_leitura': 'ok'}])
        r = confronto.confrontar_arquivo(str(caminho), registro, conn)
        assert r.assinaturas_ok is True   # arquivo íntegro
        assert r.valores_ok is False      # Timescale diverge do arquivo
        assert len(r.divergencias) == 1
        assert r.divergencias[0]['sensor_id'] == 'SNR-1'
        assert r.divergencias[0]['valor_arquivo'] == 96.83
        assert r.divergencias[0]['valor_timescale'] == 42.00
    finally:
        _limpar(conn)
        conn.close()


def test_confronto_detecta_ausencia_no_timescale(tmp_path):
    caminho, registro = _gerar_arquivo(tmp_path)
    conn = timescale.conectar(DSN)
    try:
        _limpar(conn)  # nada inserido → linha do arquivo não existe no Timescale
        r = confronto.confrontar_arquivo(str(caminho), registro, conn)
        assert r.valores_ok is False
        assert r.divergencias[0]['valor_timescale'] is None
    finally:
        _limpar(conn)
        conn.close()


def test_confronto_tolera_subsegundo_no_timescale(tmp_path):
    """C-T2: writer com timestamp em microssegundos (simulador_continuo/backfill_demo)
    não pode gerar falsa divergência + falsa injeção para a mesma leitura real.
    A chave de confronto deve ser truncada a whole-second em ambos os lados."""
    caminho, registro = _gerar_arquivo(tmp_path)  # linha em 03:01:00.000000 (whole-second)
    conn = timescale.conectar(DSN)
    try:
        _limpar(conn)
        timescale.inserir_leituras(
            conn, 'SITE-1', 'COL-CONF',
            [{'timestamp': datetime(2026, 7, 16, 3, 1, 0, 500000, tzinfo=timezone.utc),
              'sensor_id': 'SNR-1', 'area_id': 'EXPURGO', 'tipo_medida': 'temperatura',
              'valor': 96.83, 'unidade': 'C', 'protocolo_origem': '4-20ma',
              'status_leitura': 'ok'}])
        r = confronto.confrontar_arquivo(str(caminho), registro, conn)
        assert r.valores_ok is True
        assert r.divergencias == []
        assert r.injetadas_timescale == []
    finally:
        _limpar(conn)
        conn.close()


def test_confronto_detecta_injecao_no_timescale(tmp_path):
    # arquivo com 2 linhas (03:01 e 03:03) → janela cobre 03:02 (injeção ENTRE linhas)
    caminho, registro = _gerar_arquivo(tmp_path, leituras=[
        (datetime(2026, 7, 16, 3, 1, 0, tzinfo=timezone.utc), 96.83),
        (datetime(2026, 7, 16, 3, 3, 0, tzinfo=timezone.utc), 97.10)])
    conn = timescale.conectar(DSN)
    try:
        _limpar(conn)
        base = {'sensor_id': 'SNR-1', 'area_id': 'EXPURGO', 'tipo_medida': 'temperatura',
                'unidade': 'C', 'protocolo_origem': '4-20ma', 'status_leitura': 'ok'}
        timescale.inserir_leituras(conn, 'SITE-1', 'COL-CONF', [
            {**base, 'timestamp': datetime(2026, 7, 16, 3, 1, 0, tzinfo=timezone.utc), 'valor': 96.83},
            {**base, 'timestamp': datetime(2026, 7, 16, 3, 3, 0, tzinfo=timezone.utc), 'valor': 97.10},
            {**base, 'timestamp': datetime(2026, 7, 16, 3, 2, 0, tzinfo=timezone.utc), 'valor': 50.00}])  # injetada
        r = confronto.confrontar_arquivo(str(caminho), registro, conn)
        assert r.assinaturas_ok is True
        assert r.valores_ok is False
        assert len(r.injetadas_timescale) == 1
        assert r.divergencias == []  # as 2 linhas do arquivo batem; só há injeção
    finally:
        _limpar(conn)
        conn.close()


def test_confrontar_periodo_agrega_por_dia(tmp_path):
    caminho, registro = _gerar_arquivo(tmp_path)  # gera d/COL-CONF/2026-07-16_leituras.txt
    diretorio = str(tmp_path / "d" / "COL-CONF")
    conn = timescale.conectar(DSN)
    try:
        _limpar(conn)
        timescale.inserir_leituras(
            conn, 'SITE-1', 'COL-CONF',
            [{'timestamp': datetime(2026, 7, 16, 3, 1, 0, tzinfo=timezone.utc),
              'sensor_id': 'SNR-1', 'area_id': 'EXPURGO', 'tipo_medida': 'temperatura',
              'valor': 96.83, 'unidade': 'C', 'protocolo_origem': '4-20ma',
              'status_leitura': 'ok'}])
        resultados = confronto.confrontar_periodo(
            diretorio, 'COL-CONF', ['2026-07-16'], registro, conn)
        assert len(resultados) == 1
        assert resultados[0].valores_ok is True
    finally:
        _limpar(conn)
        conn.close()
