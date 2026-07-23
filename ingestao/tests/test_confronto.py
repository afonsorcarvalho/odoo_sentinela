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


def _gerar_arquivo(tmp_path, leituras=None, selar=True):
    # ts SEMPRE tz-aware (UTC aqui) — o writer emite offset e o confronto exige
    # timestamp aware (_ts_utc_iso levanta em naive).
    leituras = leituras or [(datetime(2026, 7, 16, 3, 1, 0, tzinfo=timezone.utc), 96.83)]
    assinador = AssinadorSoftware(str(tmp_path / "k.pem"))
    arq = ArquivoDiario('COL-CONF', 'HUB-1', '2.3.1', '+00:00', str(tmp_path / "d"),
                        assinador, cliente_id='CLI-1', site_id='SITE-1')
    for ts, valor in leituras:
        arq.registrar(_leitura(ts, valor))
    if selar:
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


def test_confrontar_periodo_arquivo_ausente_sem_conn(tmp_path):
    # branch de arquivo ausente retorna antes de tocar conn — conn=None é seguro.
    diretorio_vazio = str(tmp_path / "vazio")
    resultados = confronto.confrontar_periodo(
        diretorio_vazio, 'X', ['2026-07-16'], 'ingestao/coletores_conhecidos.json', conn=None)
    assert len(resultados) == 1
    r = resultados[0]
    assert r.assinaturas_ok is False
    assert r.valores_ok is False
    assert 'ausente' in r.motivo


def test_main_retorna_1_quando_arquivo_ausente(tmp_path, capsys):
    diretorio_vazio = str(tmp_path / "vazio")
    registro = str(tmp_path / "reg.json")
    argv = ['--diretorio', diretorio_vazio, '--coletor', 'X',
            '--de', '2026-07-16', '--ate', '2026-07-16',
            '--registro', registro, '--dsn', DSN]
    assert confronto.main(argv) == 1


def test_main_retorna_0_quando_dia_limpo(tmp_path, capsys):
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
        argv = ['--diretorio', diretorio, '--coletor', 'COL-CONF',
                '--de', '2026-07-16', '--ate', '2026-07-16',
                '--registro', registro, '--dsn', DSN]
        assert confronto.main(argv) == 0
    finally:
        _limpar(conn)
        conn.close()


def test_confronto_detecta_injecao_em_arquivo_footerless(tmp_path):
    """FIX C1: arquivo sem rodapé (crash não-recuperado, status 'incompleto') NÃO
    pode desligar a detecção de injeção. Um atacante que mata o coletor no meio
    do dia ganharia uma janela livre de detecção se o count-match ficasse restrito
    a arquivos selados. A janela [min_ts, max_ts] só cobre linhas já verificadas
    por cadeia — uma injeção ENTRE duas linhas reais é sempre prova de fabricação,
    selado ou não."""
    caminho, registro = _gerar_arquivo(tmp_path, leituras=[
        (datetime(2026, 7, 16, 3, 1, 0, tzinfo=timezone.utc), 96.83),
        (datetime(2026, 7, 16, 3, 3, 0, tzinfo=timezone.utc), 97.10)], selar=False)
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
        assert r.arquivo_nao_fechado is True
        assert r.assinaturas_ok is True
        assert r.valores_ok is False
        assert len(r.injetadas_timescale) == 1
    finally:
        _limpar(conn)
        conn.close()


def test_confronto_rejeita_arquivo_de_outro_coletor(tmp_path):
    """FIX I2: um arquivo válido e assinado, mas de um coletor DIFERENTE do
    solicitado, colocado no lugar esperado não pode passar por confronto limpo —
    ele nunca seria comparado contra os dados do coletor certo."""
    caminho, registro = _gerar_arquivo(tmp_path)  # arquivo é de COL-CONF
    conn = timescale.conectar(DSN)
    try:
        _limpar(conn)
        r = confronto.confrontar_arquivo(
            str(caminho), registro, conn,
            coletor_esperado='OUTRO-COLETOR', data_esperada='2026-07-16')
        assert r.assinaturas_ok is False
        assert r.valores_ok is False
        assert 'identidade' in r.motivo
    finally:
        _limpar(conn)
        conn.close()


def test_confronto_dia_vazio_com_injecao_detecta(tmp_path):
    """FIX I1: branch de linhas vazias (rv.leituras == []) ainda tem que rodar
    count-match. Gera um arquivo selado com ZERO leituras usando os métodos
    internos do ArquivoDiario (_abrir + selar sem registrar nenhuma linha) —
    produz cabeçalho + hdr_sig + rodapé, sem corpo, corretamente assinado."""
    assinador = AssinadorSoftware(str(tmp_path / "k.pem"))
    arq = ArquivoDiario('COL-CONF', 'HUB-1', '2.3.1', '+00:00', str(tmp_path / "d"),
                        assinador, cliente_id='CLI-1', site_id='SITE-1')
    arq._abrir('2026-07-16')
    arq.selar('2026-07-16')
    registro = str(tmp_path / "reg.json")
    registro_coletores.registrar_coletor(registro, 'COL-CONF', assinador.chave_publica_pem())
    caminho = arq.caminho('2026-07-16')

    conn = timescale.conectar(DSN)
    try:
        _limpar(conn)
        timescale.inserir_leituras(
            conn, 'SITE-1', 'COL-CONF',
            [{'timestamp': datetime(2026, 7, 16, 5, 0, 0, tzinfo=timezone.utc),
              'sensor_id': 'SNR-9', 'area_id': 'EXPURGO', 'tipo_medida': 'temperatura',
              'valor': 12.34, 'unidade': 'C', 'protocolo_origem': '4-20ma',
              'status_leitura': 'ok'}])  # fabricada: dia assinado sem nenhuma leitura
        r = confronto.confrontar_arquivo(str(caminho), registro, conn)
        assert r.assinaturas_ok is True
        assert r.valores_ok is False
        assert len(r.injetadas_timescale) == 1
    finally:
        _limpar(conn)
        conn.close()


def test_main_retorna_2_quando_periodo_vazio_ou_invertido(tmp_path):
    """FIX M1: --de posterior a --ate produz range vazio; um gate de auditoria
    legal não pode dar exit 0 (all-clear) sobre nenhum dia confrontado."""
    diretorio_vazio = str(tmp_path / "vazio")
    registro = str(tmp_path / "reg.json")
    argv = ['--diretorio', diretorio_vazio, '--coletor', 'X',
            '--de', '2026-07-20', '--ate', '2026-07-16',  # invertido
            '--registro', registro, '--dsn', DSN]
    assert confronto.main(argv) != 0
    assert confronto.main(argv) == 2


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
