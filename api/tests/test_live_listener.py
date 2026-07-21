import asyncio
from datetime import datetime, timezone

from api import live, live_listener
from ingestao.timescale import conectar

DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'
SENSOR_CODE_TESTE = 'SNR-LIVE-LISTENER-TEST-01'


def _limpar():
    conn = conectar(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sensor_reading WHERE sensor_id = %s", (SENSOR_CODE_TESTE,))
        conn.commit()
    finally:
        conn.close()


def test_escutar_publica_no_registry_quando_trigger_dispara():
    async def cenario():
        _limpar()
        fila = live.registrar(SENSOR_CODE_TESTE, ['SITE-TEST'])
        task = asyncio.create_task(live_listener.escutar())
        try:
            await asyncio.sleep(0.5)  # da tempo do listener conectar e comecar a escutar

            conn = conectar(DSN)
            try:
                agora = datetime.now(timezone.utc)
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO sensor_reading "
                        "(time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            agora, 'SITE-TEST', 'COL-TEST', SENSOR_CODE_TESTE,
                            'AREA-TEST', 'temperatura', 18.2, 'C', '4-20ma', 'ok',
                        ),
                    )
                conn.commit()
            finally:
                conn.close()

            item = await asyncio.wait_for(fila.get(), timeout=3)
            assert item['sensor_id'] == SENSOR_CODE_TESTE
            assert item['site_id'] == 'SITE-TEST'
            assert item['valor'] == 18.2
        finally:
            task.cancel()
            live.remover(SENSOR_CODE_TESTE, fila)
            _limpar()

    asyncio.run(cenario())
