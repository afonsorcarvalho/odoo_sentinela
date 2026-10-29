from datetime import date, datetime, timedelta, timezone

from api.relatorio_dados import buscar_buckets, granularidade
from ingestao.timescale import conectar

DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'
SENSOR_CODE = 'SNR-SIM-TEMP-01'
SITE = 'SITE-SIM-0001'
D = date(2026, 1, 10)


def _limpar(conn):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM sensor_reading WHERE sensor_id = %s", (SENSOR_CODE,))
    conn.commit()


def _inserir(conn, leituras):
    with conn.cursor() as cur:
        for ts, valor, status in leituras:
            cur.execute(
                "INSERT INTO sensor_reading "
                "(time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (ts, SITE, 'COL-SIM-0001', SENSOR_CODE, 'AREA-SIM-EXPURGO', 'temperatura', valor, 'C', '4-20ma', status),
            )
    conn.commit()


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def _com_dados(leituras, inicio, fim, gran, sites=(SITE,)):
    conn = conectar(DSN)
    try:
        _limpar(conn)
        _inserir(conn, leituras)
        return buscar_buckets(conn, SENSOR_CODE, inicio, fim, gran, list(sites))
    finally:
        _limpar(conn)
        conn.close()


def test_granularidade():
    assert granularidade(D, D) == 'hora'
    assert granularidade(D, D + timedelta(days=61)) == 'dia'
    assert granularidade(D, D + timedelta(days=62)) == 'mes'


def test_hora_retorna_24_buckets_com_sem_dados():
    # 10:15 local (UTC-3) = 13:15 UTC
    itens = _com_dados([(_utc(2026, 1, 10, 13, 15), 21.0, 'ok')], D, D, 'hora')
    assert len(itens) == 24
    assert itens[10]['estado'] == 'ok'
    for i, it in enumerate(itens):
        if i != 10:
            assert it['estado'] == 'sem_dados'
            assert it['avg'] is None


def test_borda_meia_noite_local():
    # 2026-01-11 02:30 UTC = 10/01 23:30 local
    itens = _com_dados([(_utc(2026, 1, 11, 2, 30), 22.0, 'ok')], D, date(2026, 1, 11), 'dia')
    assert len(itens) == 2
    assert itens[0]['estado'] == 'ok'
    assert itens[0]['n_ok'] == 1
    assert itens[1]['estado'] == 'sem_dados'


def test_falha_excluida():
    itens = _com_dados(
        [
            (_utc(2026, 1, 10, 13, 10), 20.0, 'ok'),
            (_utc(2026, 1, 10, 13, 20), 0.0, 'falha_sensor'),
            (_utc(2026, 1, 10, 15, 10), 0.0, 'falha_sensor'),
        ],
        D, D, 'hora',
    )
    assert itens[10]['avg'] == 20.0
    assert itens[10]['min'] == 20.0
    assert itens[10]['n_ok'] == 1
    assert itens[10]['n_falha'] == 1
    assert itens[12]['estado'] == 'falha_instrumento'
    assert itens[12]['avg'] is None


def test_mes():
    itens = _com_dados(
        [(_utc(2026, 2, 15, 12, 0), 20.0, 'ok')], D, date(2026, 4, 10), 'mes'
    )
    assert len(itens) == 4
    assert itens[0]['bucket'] == datetime(2026, 1, 1, 3, 0, tzinfo=timezone.utc)
    assert itens[1]['estado'] == 'ok'


def test_site_nao_permitido_retorna_sem_dados():
    itens = _com_dados(
        [(_utc(2026, 1, 10, 13, 15), 21.0, 'ok')], D, D, 'hora', sites=('OUTRO',)
    )
    assert len(itens) == 24
    assert all(it['estado'] == 'sem_dados' for it in itens)
