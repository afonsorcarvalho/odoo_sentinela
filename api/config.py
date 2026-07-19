import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ingestao import odoo_cliente

from .auth import exigir_admin, verificar_token
from .odoo import SITE_CODE, get_cliente_servico

router = APIRouter()

_DEFAULT_CAROUSEL_INTERVAL_MS = 3000


class LayoutBody(BaseModel):
    layout: dict


def _site_id_do_code(cliente):
    sites = odoo_cliente.executar(
        cliente, 'sensor_monitor.site', 'search_read',
        [('site_code', '=', SITE_CODE)], fields=['id'],
    )
    return sites[0]['id'] if sites else None


def obter_config(cliente):
    site_id = _site_id_do_code(cliente)
    if site_id is None:
        return {'carousel_interval_ms': _DEFAULT_CAROUSEL_INTERVAL_MS, 'layout': None}

    configs = odoo_cliente.executar(
        cliente, 'sensor_monitor.dashboard.config', 'search_read',
        [('site_id', '=', site_id)], fields=['carousel_interval_ms', 'layout_json'],
    )
    if not configs:
        return {'carousel_interval_ms': _DEFAULT_CAROUSEL_INTERVAL_MS, 'layout': None}

    cfg = configs[0]
    layout = json.loads(cfg['layout_json']) if cfg.get('layout_json') else None
    return {'carousel_interval_ms': cfg['carousel_interval_ms'], 'layout': layout}


@router.get('/config')
def get_config(cliente=Depends(get_cliente_servico), _claims=Depends(verificar_token)):
    return obter_config(cliente)


@router.put('/config/layout')
def put_layout(body: LayoutBody, cliente=Depends(get_cliente_servico), _claims=Depends(exigir_admin)):
    layout = body.layout
    if not isinstance(layout, dict) or not isinstance(layout.get('version'), int) \
            or not isinstance(layout.get('widgets'), list):
        raise HTTPException(status_code=400, detail='layout inválido: requer version(int) e widgets(list)')

    site_id = _site_id_do_code(cliente)
    if site_id is None:
        raise HTTPException(status_code=404, detail=f'site {SITE_CODE} não encontrado')

    valores = {'layout_json': json.dumps(layout), 'layout_version': layout['version']}
    existentes = odoo_cliente.executar(
        cliente, 'sensor_monitor.dashboard.config', 'search',
        [('site_id', '=', site_id)],
    )
    if existentes:
        odoo_cliente.executar(cliente, 'sensor_monitor.dashboard.config', 'write', existentes, valores)
    else:
        odoo_cliente.executar(
            cliente, 'sensor_monitor.dashboard.config', 'create', {'site_id': site_id, **valores},
        )
    return {'layout': layout}
