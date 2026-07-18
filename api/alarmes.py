from fastapi import APIRouter, Depends

from ingestao import odoo_cliente

from .auth import verificar_token
from .odoo import get_cliente_servico

router = APIRouter()

_CAMPOS_EVENTO = [
    'sensor_id', 'area_id', 'tipo_violacao', 'status',
    'timestamp_deteccao', 'valor_lido', 'limite_configurado_snapshot', 'data_resolucao',
]


def _serializar_evento(evento, sensores_por_id, areas_por_id):
    sensor = sensores_por_id[evento['sensor_id'][0]]
    area = areas_por_id[evento['area_id'][0]]
    return {
        'id': evento['id'],
        'sensor_code': sensor['sensor_code'],
        'area': {'area_code': area['area_code'], 'name': area['name']},
        'tipo_violacao': evento['tipo_violacao'],
        'status': evento['status'],
        'timestamp_deteccao': evento['timestamp_deteccao'],
        'valor_lido': evento['valor_lido'],
        'limite_configurado_snapshot': evento['limite_configurado_snapshot'],
        'data_resolucao': evento['data_resolucao'],
    }


@router.get('/alarmes')
def get_alarmes(cliente=Depends(get_cliente_servico), _claims=Depends(verificar_token)):
    eventos = odoo_cliente.executar(
        cliente, 'sensor_monitor.alarm.event', 'search_read', [],
        fields=_CAMPOS_EVENTO, order='timestamp_deteccao desc', limit=50,
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
            cliente, 'sensor_monitor.area', 'read', area_ids, fields=['area_code', 'name'],
        )
        areas_por_id = {a['id']: a for a in areas}

    return [_serializar_evento(e, sensores_por_id, areas_por_id) for e in eventos]
