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
        versao = dados.get('config_version_aplicada')
        if versao:
            # rede de segurança: se o 'applied' one-shot (OuvinteReport) se
            # perder, o heartbeat retido do hub eventualmente fecha o drift
            # aqui. Best-effort — presença não pode cair por causa disto.
            from .config_report import registrar_versao_aplicada
            from .odoo import get_cliente_servico
            try:
                registrar_versao_aplicada(get_cliente_servico(), code, int(versao),
                                          dados.get('heartbeat_ts'))
            except Exception:
                pass

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
