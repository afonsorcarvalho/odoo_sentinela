import os
from datetime import datetime, timezone

import yaml
from fastapi import APIRouter, Header, HTTPException

from . import mqtt as api_mqtt
from .config_publisher import escrever_config_sftp, serializar_config_hub
from .odoo import get_cliente_servico

router = APIRouter()
_SECRET = os.environ.get('CONFIG_PUBLISH_SECRET', '')


@router.post('/internal/hub/{hub_code}/publicar-config')
def publicar_config(hub_code: str, x_config_secret: str = Header(default='')):
    if not _SECRET or x_config_secret != _SECRET:
        raise HTTPException(status_code=401, detail='secret inválido')
    cliente = get_cliente_servico()
    cfg = serializar_config_hub(cliente, hub_code)
    versao = cfg['version']
    remoto = escrever_config_sftp(hub_code, versao, yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))
    api_mqtt.publicar(
        f'sentinela/config/notify/hub/{hub_code}',
        {'version': versao, 'publicado_em': datetime.now(timezone.utc).isoformat()},
        retain=True)
    return {'version': versao, 'arquivo': remoto}
