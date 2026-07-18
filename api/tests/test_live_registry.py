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
