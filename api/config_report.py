from datetime import datetime, timezone

from .mqtt import OuvinteMqtt
from .odoo import get_cliente_servico
from ingestao import odoo_cliente


def _formatar_datetime_odoo(valor_iso):
    # XML-RPC do Odoo rejeita string ISO com timezone (ex.:
    # '2026-07-22T10:00:00+00:00') no campo Datetime — o Odoo guarda Datetime
    # em UTC "naive", então normaliza para UTC antes de tirar o tzinfo
    # (mesmo padrão de ingestao.odoo_cliente._timestamp_arquivo_para_utc).
    if not valor_iso:
        return False
    dt = datetime.fromisoformat(valor_iso)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime('%Y-%m-%d %H:%M:%S')


class OuvinteReport:
    def __init__(self):
        self._ouvinte = None

    def _on(self, topico, dados):
        if dados.get('status') and dados['status'] != 'ok':
            return
        code = topico.rsplit('/', 1)[-1]
        versao = dados.get('version')
        if versao is None:
            return
        cliente = get_cliente_servico()
        hubs = odoo_cliente.executar(cliente, 'sensor_monitor.hub', 'search',
                                      [('hub_code', '=', code)])
        if not hubs:
            return
        odoo_cliente.executar(cliente, 'sensor_monitor.hub', 'write', [hubs[0]], {
            'config_version_aplicada': versao,
            'config_version_reportada_em': _formatar_datetime_odoo(dados.get('aplicado_em')),
        })

    def iniciar(self):
        self._ouvinte = OuvinteMqtt(self._on)
        self._ouvinte.iniciar(['sentinela/config/applied/hub/#'])

    def parar(self):
        if self._ouvinte:
            self._ouvinte.parar()


OUVINTE_REPORT = OuvinteReport()
