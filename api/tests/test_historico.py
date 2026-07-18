from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from api.main import app
from ingestao.timescale import conectar

client = TestClient(app)
DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'
SENSOR_CODE = 'SNR-SIM-TEMP-01'


def _headers():
    resposta = client.post('/auth/login', json={'usuario': 'admin', 'senha': 'admin'})
    token = resposta.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def _limpar():
    conn = conectar(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sensor_reading WHERE sensor_id = %s", (SENSOR_CODE,))
        conn.commit()
    finally:
        conn.close()


def test_historico_1h_raw_retorna_pontos_inseridos():
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
                    agora - timedelta(minutes=5), 'SITE-SIM-0001', 'COL-SIM-0001', SENSOR_CODE,
                    'AREA-SIM-EXPURGO', 'temperatura', 20.1, 'C', '4-20ma', 'ok',
                ),
            )
        conn.commit()

        resposta = client.get(f'/sensores/{SENSOR_CODE}/historico', params={'window': '1h'}, headers=_headers())
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo['sensor_code'] == SENSOR_CODE
        assert corpo['window'] == '1h'
        assert corpo['resolution'] == 'raw'
        assert len(corpo['points']) == 1
        assert corpo['points'][0]['value'] == 20.1
        assert 'ts' in corpo['points'][0]
    finally:
        _limpar()
        conn.close()


def test_historico_24h_agregado_apos_refresh():
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
                    agora - timedelta(minutes=5), 'SITE-SIM-0001', 'COL-SIM-0001', SENSOR_CODE,
                    'AREA-SIM-EXPURGO', 'temperatura', 22.3, 'C', '4-20ma', 'ok',
                ),
            )
        conn.commit()
        # refresh_continuous_aggregate() do Timescale so' roda fora de bloco de
        # transacao — autocommit so' pra essa chamada, restaurado em seguida.
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "CALL refresh_continuous_aggregate('sensor_reading_hourly', %s, %s)",
                (agora - timedelta(hours=2), agora + timedelta(hours=1)),
            )
        conn.autocommit = False

        resposta = client.get(f'/sensores/{SENSOR_CODE}/historico', params={'window': '24h'}, headers=_headers())
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo['resolution'] == 'agg'
        assert len(corpo['points']) >= 1
        assert corpo['points'][0]['avg'] == 22.3
    finally:
        _limpar()
        conn.close()


def test_historico_sensor_inexistente_retorna_404():
    resposta = client.get('/sensores/SNR-NAO-EXISTE-XYZ/historico', params={'window': '1h'}, headers=_headers())
    assert resposta.status_code == 404


def test_historico_window_invalida_retorna_422():
    resposta = client.get(f'/sensores/{SENSOR_CODE}/historico', params={'window': '99x'}, headers=_headers())
    assert resposta.status_code == 422


def test_historico_sem_auth_retorna_401():
    resposta = client.get(f'/sensores/{SENSOR_CODE}/historico', params={'window': '1h'})
    assert resposta.status_code == 401
