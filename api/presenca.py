import time

from .mqtt import OuvinteMqtt

_STALE_S = 90


class Rastreador:
    def __init__(self):
        self._estado = {}
        self._ouvinte = None

    def atualizar(self, topico, dados):
        # topico: sentinela/status/hub/<code>
        code = topico.rsplit('/', 1)[-1]
        self._estado[code] = dados

    def estado(self, hub_code):
        d = self._estado.get(hub_code)
        if not d:
            return None
        idade = time.time() - d.get('heartbeat_ts', 0)
        return {'estado': d.get('estado'), 'idade_s': idade, 'stale': idade > _STALE_S}

    def iniciar(self):
        self._ouvinte = OuvinteMqtt(self.atualizar)
        self._ouvinte.iniciar(['sentinela/status/hub/#'])

    def parar(self):
        if self._ouvinte:
            self._ouvinte.parar()


RASTREADOR = Rastreador()
