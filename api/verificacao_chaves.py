"""Resolve as chaves publicas dos coletores a partir do Odoo (fonte unica),
com cache de TTL curto. Usado pelo verificador do portal.
"""
import time

from ingestao import odoo_cliente

from .odoo import get_cliente_servico

_TTL_S = 60
_cache = {'em': None, 'dados': None}


def invalidar_cache():
    _cache['em'] = None
    _cache['dados'] = None


def chaves_do_odoo(force=False):
    agora = time.monotonic()
    if not force and _cache['dados'] is not None and (agora - _cache['em']) < _TTL_S:
        return _cache['dados']
    cliente = get_cliente_servico()
    linhas = odoo_cliente.executar(
        cliente, 'sensor_monitor.coletor', 'search_read', [],
        fields=['coletor_code', 'pubkey_pem'])
    dados = {l['coletor_code']: l['pubkey_pem'] for l in linhas if l.get('pubkey_pem')}
    _cache['dados'] = dados
    _cache['em'] = agora
    return dados
