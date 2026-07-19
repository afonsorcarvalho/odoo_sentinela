import asyncio

import pytest

from api import live


def test_registrar_e_publicar_entrega_na_fila():
    async def cenario():
        fila = live.registrar('SNR-1')
        live.publicar('SNR-1', {'valor': 1})
        item = await asyncio.wait_for(fila.get(), timeout=1)
        assert item == {'valor': 1}
        live.remover('SNR-1', fila)

    asyncio.run(cenario())


def test_publicar_sem_inscritos_nao_lanca_erro():
    live.publicar('SNR-SEM-INSCRITOS', {'valor': 2})


def test_remover_impede_entrega_futura():
    async def cenario():
        fila = live.registrar('SNR-2')
        live.remover('SNR-2', fila)
        live.publicar('SNR-2', {'valor': 3})
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(fila.get(), timeout=0.2)

    asyncio.run(cenario())


def test_registrar_global_e_publicar_entrega_em_todas_as_filas_globais():
    async def cenario():
        fila = live.registrar_global()
        live.publicar('QUALQUER-SENSOR', {'sensor_id': 'QUALQUER-SENSOR', 'valor': 42})
        item = await asyncio.wait_for(fila.get(), timeout=1)
        assert item == {'sensor_id': 'QUALQUER-SENSOR', 'valor': 42}
        live.remover_global(fila)

    asyncio.run(cenario())


def test_remover_global_impede_entrega_futura():
    async def cenario():
        fila = live.registrar_global()
        live.remover_global(fila)
        live.publicar('SNR-X', {'valor': 1})
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(fila.get(), timeout=0.2)

    asyncio.run(cenario())


def test_publicar_alimenta_fila_por_sensor_e_fila_global_ao_mesmo_tempo():
    async def cenario():
        fila_sensor = live.registrar('SNR-Y')
        fila_global = live.registrar_global()
        live.publicar('SNR-Y', {'sensor_id': 'SNR-Y', 'valor': 7})

        item_sensor = await asyncio.wait_for(fila_sensor.get(), timeout=1)
        item_global = await asyncio.wait_for(fila_global.get(), timeout=1)
        assert item_sensor == item_global == {'sensor_id': 'SNR-Y', 'valor': 7}

        live.remover('SNR-Y', fila_sensor)
        live.remover_global(fila_global)

    asyncio.run(cenario())
