from fastapi import APIRouter, Depends

from ingestao import odoo_cliente

from .auth import verificar_token
from .odoo import SITE_CODE, get_cliente_servico

router = APIRouter()

_DEFAULT_CAROUSEL_INTERVAL_MS = 3000


def obter_config(cliente):
    sites = odoo_cliente.executar(
        cliente, 'sensor_monitor.site', 'search_read',
        [('site_code', '=', SITE_CODE)], fields=['id'],
    )
    if not sites:
        return {'carousel_interval_ms': _DEFAULT_CAROUSEL_INTERVAL_MS}

    configs = odoo_cliente.executar(
        cliente, 'sensor_monitor.dashboard.config', 'search_read',
        [('site_id', '=', sites[0]['id'])], fields=['carousel_interval_ms'],
    )
    if not configs:
        return {'carousel_interval_ms': _DEFAULT_CAROUSEL_INTERVAL_MS}

    return {'carousel_interval_ms': configs[0]['carousel_interval_ms']}


@router.get('/config')
def get_config(cliente=Depends(get_cliente_servico), _claims=Depends(verificar_token)):
    return obter_config(cliente)
