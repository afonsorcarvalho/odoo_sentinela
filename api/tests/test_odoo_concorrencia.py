import threading

from api.odoo import get_cliente_servico
from ingestao import odoo_cliente


def test_chamadas_concorrentes_nao_colidem():
    cliente = get_cliente_servico()
    erros = []

    def chamar():
        try:
            odoo_cliente.executar(cliente, 'sensor_monitor.sensor', 'search_read', [], fields=['sensor_code'])
        except Exception as exc:  # noqa: BLE001 -- queremos capturar QUALQUER falha de concorrencia
            erros.append(exc)

    threads = [threading.Thread(target=chamar) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert erros == [], f"chamadas concorrentes falharam: {erros}"
