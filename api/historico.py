import os
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from ingestao.timescale import conectar

from . import timescale as api_timescale
from .auth import get_cliente_usuario, verificar_token
from .meta import obter_sensor
from .permissions import obter_sites_permitidos

router = APIRouter()

DSN = os.environ.get('TIMESCALE_DSN', 'postgresql://sentinela:sentinela@localhost:5433/sentinela')

_JANELAS = {
    '1h': {'resolution': 'raw', 'delta': timedelta(hours=1)},
    '24h': {'resolution': 'agg', 'tabela': 'sensor_reading_hourly', 'delta': timedelta(hours=24)},
    '7d': {'resolution': 'agg', 'tabela': 'sensor_reading_hourly', 'delta': timedelta(days=7)},
    '30d': {'resolution': 'agg', 'tabela': 'sensor_reading_daily', 'delta': timedelta(days=30)},
}


@router.get('/sensores/{sensor_code}/historico')
def get_historico(
    sensor_code: str,
    window: Literal['1h', '24h', '7d', '30d'],
    cliente=Depends(get_cliente_usuario),
    _claims=Depends(verificar_token),
):
    if obter_sensor(cliente, sensor_code) is None:
        raise HTTPException(status_code=404, detail=f"sensor '{sensor_code}' não encontrado")

    sites_permitidos = obter_sites_permitidos(cliente)
    config = _JANELAS[window]
    desde = datetime.now(timezone.utc) - config['delta']

    conn = conectar(DSN)
    try:
        if config['resolution'] == 'raw':
            linhas = api_timescale.buscar_raw(conn, sensor_code, desde, sites_permitidos)
            points = [{'ts': int(linha['time'].timestamp() * 1000), 'value': linha['valor']} for linha in linhas]
        else:
            linhas = api_timescale.buscar_agregado(conn, sensor_code, config['tabela'], desde, sites_permitidos)
            points = [
                {
                    'ts': int(linha['bucket'].timestamp() * 1000),
                    'min': linha['min'], 'max': linha['max'], 'avg': linha['avg'],
                }
                for linha in linhas
            ]
    finally:
        conn.close()

    return {
        'sensor_code': sensor_code,
        'window': window,
        'resolution': config['resolution'],
        'points': points,
    }
