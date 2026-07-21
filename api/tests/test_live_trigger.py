import json
import select
from datetime import datetime, timezone

import psycopg2

from ingestao.timescale import conectar

DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'
SENSOR_CODE_TESTE = 'SNR-LIVE-TRIGGER-TEST-01'


def _limpar():
    conn = conectar(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sensor_reading WHERE sensor_id = %s", (SENSOR_CODE_TESTE,))
        conn.commit()
    finally:
        conn.close()


def test_trigger_dispara_notify_no_insert():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    _limpar()
    try:
        with conn.cursor() as cur:
            cur.execute("LISTEN sensor_reading_new;")

        conn_insert = conectar(DSN)
        try:
            agora = datetime.now(timezone.utc)
            with conn_insert.cursor() as cur:
                cur.execute(
                    "INSERT INTO sensor_reading "
                    "(time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        agora, 'SITE-TEST', 'COL-TEST', SENSOR_CODE_TESTE,
                        'AREA-TEST', 'temperatura', 23.4, 'C', '4-20ma', 'ok',
                    ),
                )
            conn_insert.commit()
        finally:
            conn_insert.close()

        prontos = select.select([conn], [], [], 3)
        assert prontos[0], "nenhuma notificacao recebida em 3s — trigger nao disparou?"
        conn.poll()
        assert conn.notifies, "select() retornou mas conn.notifies esta vazio"
        notificacao = conn.notifies.pop(0)
        assert notificacao.channel == 'sensor_reading_new'
        payload = json.loads(notificacao.payload)
        assert payload['sensor_id'] == SENSOR_CODE_TESTE
        assert payload['site_id'] == 'SITE-TEST'
        assert payload['valor'] == 23.4
    finally:
        _limpar()
        conn.close()
