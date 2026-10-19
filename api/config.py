import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ingestao import odoo_cliente

from .auth import exigir_admin, get_cliente_usuario
from .odoo import SITE_CODE

router = APIRouter()

_DEFAULT_CAROUSEL_INTERVAL_MS = 3000
_DEFAULT_CAROUSEL_TRANSITION_MS = 300


class LayoutBody(BaseModel):
    layout: dict


def _site_id_do_usuario(cliente, site_code=None):
    """Site do usuário logado. `cliente` é a sessão do usuário, então o
    search_read já vem filtrado pelo ir.rule: só aparecem sites permitidos.

    Com `site_code` explícito, ele tem de estar entre os permitidos (senão
    404, sem distinguir "não existe" de "não é seu"). Sem ele: SITE_CODE do
    processo se o usuário o enxerga, senão o primeiro por código. A escolha de
    site no frontend (cliente multi-site) ainda não existe.
    """
    sites = odoo_cliente.executar(
        cliente, 'sensor_monitor.site', 'search_read', [], fields=['id', 'site_code'],
    )
    por_codigo = {s['site_code']: s['id'] for s in sites}
    if site_code is not None:
        if site_code not in por_codigo:
            raise HTTPException(status_code=404, detail='site não encontrado')
        return por_codigo[site_code]
    if SITE_CODE in por_codigo:
        return por_codigo[SITE_CODE]
    return por_codigo[min(por_codigo)] if por_codigo else None


def _default_config():
    return {
        'carousel_interval_ms': _DEFAULT_CAROUSEL_INTERVAL_MS,
        'carousel_transition_ms': _DEFAULT_CAROUSEL_TRANSITION_MS,
        'layout': None,
    }


def obter_config(cliente, site_code=None):
    site_id = _site_id_do_usuario(cliente, site_code)
    if site_id is None:
        return _default_config()

    configs = odoo_cliente.executar(
        cliente, 'sensor_monitor.dashboard.config', 'search_read',
        [('site_id', '=', site_id)],
        fields=['carousel_interval_ms', 'carousel_transition_ms', 'layout_json'],
    )
    if not configs:
        return _default_config()

    cfg = configs[0]
    layout = json.loads(cfg['layout_json']) if cfg.get('layout_json') else None
    return {
        'carousel_interval_ms': cfg['carousel_interval_ms'],
        'carousel_transition_ms': cfg['carousel_transition_ms'],
        'layout': layout,
    }


@router.get('/config')
def get_config(site: Optional[str] = None, cliente=Depends(get_cliente_usuario)):
    return obter_config(cliente, site)


@router.put('/config/layout')
def put_layout(body: LayoutBody, site: Optional[str] = None, cliente=Depends(get_cliente_usuario),
               _claims=Depends(exigir_admin)):
    layout = body.layout
    if not isinstance(layout, dict) or not isinstance(layout.get('version'), int) \
            or not isinstance(layout.get('widgets'), list):
        raise HTTPException(status_code=400, detail='layout inválido: requer version(int) e widgets(list)')

    site_id = _site_id_do_usuario(cliente, site)
    if site_id is None:
        raise HTTPException(status_code=404, detail='site não encontrado')

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
