import os

os.environ.setdefault('API_JWT_SECRET', 'segredo-de-teste-pytest-nao-usar-em-producao')

import asyncio

import pytest


@pytest.fixture(autouse=True)
def _event_loop_corrente():
    # Em Python 3.9, asyncio.Queue()/Semaphore() e get_event_loop() exigem um
    # loop corrente na thread. Testes com TestClient/anyio podem deixá-la sem
    # loop, e testes síncronos que constroem o Gestor falhariam conforme a
    # ordem de execução da suíte.
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    yield
