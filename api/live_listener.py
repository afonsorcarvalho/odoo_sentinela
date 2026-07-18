import asyncio
import json
import os

import asyncpg

from . import live

DSN = os.environ.get('TIMESCALE_DSN', 'postgresql://sentinela:sentinela@localhost:5433/sentinela')
CANAL = 'sensor_reading_new'
RETRY_SEGUNDOS = 2


def _receber_notificacao(connection, pid, channel, payload):
    dados = json.loads(payload)
    live.publicar(dados['sensor_id'], dados)


async def escutar(dsn=DSN):
    while True:
        try:
            conn = await asyncpg.connect(dsn)
            desconectado = asyncio.Event()
            conn.add_termination_listener(lambda c: desconectado.set())
            try:
                await conn.add_listener(CANAL, _receber_notificacao)
                await desconectado.wait()
            finally:
                if not conn.is_closed():
                    await conn.close()
        except Exception:
            await asyncio.sleep(RETRY_SEGUNDOS)
