"""Backfill do coletores_conhecidos.json -> sensor_monitor.coletor.pubkey_pem.

Casa por coletor_code. Idempotente (write do mesmo PEM não muda nada).
Uso: PYTHONPATH=. python scripts/backfill_pubkey_odoo.py [--registro PATH]
"""
import argparse
import json
from pathlib import Path

from ingestao import odoo_cliente
from api.odoo import ODOO_URL, ODOO_DB, ODOO_USUARIO_SERVICO, ODOO_SENHA_SERVICO


def parear_registro(registro, coletores_odoo):
    por_code = {c['coletor_code']: c['id'] for c in coletores_odoo}
    return [(por_code[code], pem) for code, pem in registro.items() if code in por_code]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--registro', default='ingestao/coletores_conhecidos.json')
    args = parser.parse_args(argv)
    registro = json.loads(Path(args.registro).read_text())
    cliente = odoo_cliente.conectar(ODOO_URL, ODOO_DB, ODOO_USUARIO_SERVICO, ODOO_SENHA_SERVICO)
    coletores = odoo_cliente.executar(
        cliente, 'sensor_monitor.coletor', 'search_read', [], fields=['id', 'coletor_code'])
    pares = parear_registro(registro, coletores)
    for coletor_id, pem in pares:
        odoo_cliente.executar(cliente, 'sensor_monitor.coletor', 'write', [coletor_id], {'pubkey_pem': pem})
    print(f"backfill: {len(pares)} coletor(es) atualizado(s)")


if __name__ == '__main__':
    main()
