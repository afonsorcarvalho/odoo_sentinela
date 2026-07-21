from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException

from ingestao import odoo_cliente

from .auth import get_cliente_usuario, verificar_token

router = APIRouter()

_CAMPOS_EVENTO = [
    'sensor_id', 'area_id', 'tipo_violacao', 'status',
    'timestamp_deteccao', 'timestamp_resolucao_sensor', 'valor_lido',
    'limite_configurado_snapshot', 'usuario_responsavel_id', 'data_resolucao', 'observacoes',
]


def _para_epoch_ms(valor_odoo):
    if not valor_odoo:
        return None
    dt = datetime.strptime(valor_odoo, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _para_string_odoo(dt):
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def _serializar_evento(evento, sensores_por_id, areas_por_id):
    sensor = sensores_por_id[evento['sensor_id'][0]]
    area = areas_por_id[evento['area_id'][0]]
    return {
        'id': evento['id'],
        'sensor_code': sensor['sensor_code'],
        'area_code': area['area_code'],
        'timestamp_deteccao': _para_epoch_ms(evento['timestamp_deteccao']),
        'timestamp_resolucao_sensor': _para_epoch_ms(evento['timestamp_resolucao_sensor']),
        'valor_lido': evento['valor_lido'],
        'tipo_violacao': evento['tipo_violacao'],
        'limite_configurado_snapshot': evento['limite_configurado_snapshot'],
        'status': evento['status'],
        'usuario_responsavel': evento['usuario_responsavel_id'][1] if evento['usuario_responsavel_id'] else None,
        'data_resolucao': _para_epoch_ms(evento['data_resolucao']),
        'observacoes': evento['observacoes'] or None,
    }


def listar_alarmes(cliente, status=None, sensor_code=None, area_code=None, desde=None, ate=None):
    dominio = []
    if status:
        dominio.append(('status', '=', status))
    if sensor_code:
        sensor_ids = odoo_cliente.executar(
            cliente, 'sensor_monitor.sensor', 'search', [('sensor_code', '=', sensor_code)],
        )
        if not sensor_ids:
            raise ValueError(f"sensor '{sensor_code}' não encontrado")
        dominio.append(('sensor_id', '=', sensor_ids[0]))
    if area_code:
        area_ids = odoo_cliente.executar(
            cliente, 'sensor_monitor.area', 'search', [('area_code', '=', area_code)],
        )
        if not area_ids:
            return []
        dominio.append(('area_id', 'in', area_ids))
    if desde:
        dominio.append(('timestamp_deteccao', '>=', _para_string_odoo(desde)))
    if ate:
        dominio.append(('timestamp_deteccao', '<=', _para_string_odoo(ate)))

    eventos = odoo_cliente.executar(
        cliente, 'sensor_monitor.alarm.event', 'search_read', dominio,
        fields=_CAMPOS_EVENTO, order='timestamp_deteccao desc', limit=200,
    )

    sensor_ids = list({e['sensor_id'][0] for e in eventos})
    area_ids = list({e['area_id'][0] for e in eventos})

    sensores_por_id = {}
    if sensor_ids:
        sensores = odoo_cliente.executar(
            cliente, 'sensor_monitor.sensor', 'read', sensor_ids, fields=['sensor_code'],
        )
        sensores_por_id = {s['id']: s for s in sensores}

    areas_por_id = {}
    if area_ids:
        areas = odoo_cliente.executar(
            cliente, 'sensor_monitor.area', 'read', area_ids, fields=['area_code'],
        )
        areas_por_id = {a['id']: a for a in areas}

    return [_serializar_evento(e, sensores_por_id, areas_por_id) for e in eventos]


@router.get('/alarmes')
def get_alarmes(
    status: Optional[Literal['aberto', 'reconhecido', 'resolvido']] = None,
    sensor_code: Optional[str] = None,
    area_code: Optional[str] = None,
    desde: Optional[datetime] = None,
    ate: Optional[datetime] = None,
    cliente=Depends(get_cliente_usuario),
    _claims=Depends(verificar_token),
):
    try:
        return listar_alarmes(cliente, status, sensor_code, area_code, desde, ate)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
