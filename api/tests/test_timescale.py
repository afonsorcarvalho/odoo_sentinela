from datetime import datetime, timedelta, timezone

from api import timescale as api_timescale
from ingestao.timescale import conectar

DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'
SENSOR_CODE_TESTE = 'SNR-HIST-TEST-01'


def _limpar():
    conn = conectar(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sensor_reading WHERE sensor_id = %s", (SENSOR_CODE_TESTE,))
        conn.commit()
    finally:
        conn.close()


def test_buscar_raw_retorna_leituras_recentes():
    conn = conectar(DSN)
    _limpar()
    try:
        agora = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sensor_reading "
                "(time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    agora - timedelta(minutes=10), 'SITE-TEST', 'COL-TEST', SENSOR_CODE_TESTE,
                    'AREA-TEST', 'temperatura', 21.5, 'C', '4-20ma', 'ok',
                ),
            )
        conn.commit()

        pontos = api_timescale.buscar_raw(conn, SENSOR_CODE_TESTE, agora - timedelta(hours=1), ['SITE-TEST'])
        assert len(pontos) == 1
        assert pontos[0]['valor'] == 21.5
    finally:
        _limpar()
        conn.close()


def test_buscar_raw_nao_retorna_leitura_de_site_nao_permitido():
    conn = conectar(DSN)
    _limpar()
    try:
        agora = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sensor_reading "
                "(time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    agora - timedelta(minutes=10), 'SITE-NAO-PERMITIDO', 'COL-TEST', SENSOR_CODE_TESTE,
                    'AREA-TEST', 'temperatura', 21.5, 'C', '4-20ma', 'ok',
                ),
            )
        conn.commit()

        pontos = api_timescale.buscar_raw(conn, SENSOR_CODE_TESTE, agora - timedelta(hours=1), ['SITE-OUTRO'])
        assert pontos == []
    finally:
        _limpar()
        conn.close()


def test_buscar_agregado_retorna_bucket_apos_refresh():
    conn = conectar(DSN)
    _limpar()
    try:
        agora = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sensor_reading "
                "(time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    agora - timedelta(minutes=10), 'SITE-TEST', 'COL-TEST', SENSOR_CODE_TESTE,
                    'AREA-TEST', 'temperatura', 21.5, 'C', '4-20ma', 'ok',
                ),
            )
        conn.commit()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "CALL refresh_continuous_aggregate('sensor_reading_hourly', %s, %s)",
                (agora - timedelta(hours=2), agora + timedelta(hours=1)),
            )
        conn.autocommit = False

        pontos = api_timescale.buscar_agregado(
            conn, SENSOR_CODE_TESTE, 'sensor_reading_hourly', agora - timedelta(hours=2), ['SITE-TEST'],
        )
        assert len(pontos) == 1
        assert pontos[0]['avg'] == 21.5
    finally:
        _limpar()
        conn.close()


def test_buscar_agregado_nao_retorna_bucket_de_site_nao_permitido():
    conn = conectar(DSN)
    _limpar()
    try:
        agora = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sensor_reading "
                "(time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    agora - timedelta(minutes=10), 'SITE-TEST', 'COL-TEST', SENSOR_CODE_TESTE,
                    'AREA-TEST', 'temperatura', 21.5, 'C', '4-20ma', 'ok',
                ),
            )
        conn.commit()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "CALL refresh_continuous_aggregate('sensor_reading_hourly', %s, %s)",
                (agora - timedelta(hours=2), agora + timedelta(hours=1)),
            )
        conn.autocommit = False

        pontos = api_timescale.buscar_agregado(
            conn, SENSOR_CODE_TESTE, 'sensor_reading_hourly', agora - timedelta(hours=2), ['SITE-OUTRO'],
        )
        assert pontos == []
    finally:
        _limpar()
        conn.close()


def test_buscar_agregado_nega_quando_nao_ha_linha_raw_para_o_sensor():
    conn = conectar(DSN)
    _limpar()
    try:
        agora = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sensor_reading "
                "(time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    agora - timedelta(minutes=10), 'SITE-TEST', 'COL-TEST', SENSOR_CODE_TESTE,
                    'AREA-TEST', 'temperatura', 21.5, 'C', '4-20ma', 'ok',
                ),
            )
        conn.commit()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "CALL refresh_continuous_aggregate('sensor_reading_hourly', %s, %s)",
                (agora - timedelta(hours=2), agora + timedelta(hours=1)),
            )
        conn.autocommit = False

        # Simula retencao: apaga a linha raw, mas o bucket agregado ja calculado persiste.
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sensor_reading WHERE sensor_id = %s", (SENSOR_CODE_TESTE,))
        conn.commit()

        pontos = api_timescale.buscar_agregado(
            conn, SENSOR_CODE_TESTE, 'sensor_reading_hourly', agora - timedelta(hours=2), ['SITE-TEST'],
        )
        assert pontos == []
    finally:
        _limpar()
        conn.close()
