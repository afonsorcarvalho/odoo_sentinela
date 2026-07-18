from fastapi import APIRouter, Depends

from ingestao import odoo_cliente

from .auth import verificar_token
from .odoo import get_cliente_servico

router = APIRouter()

_CAMPOS_EVENTO = [
    'sensor_id', 'area_id', 'tipo_violacao', 'status',
    'timestamp_deteccao', 'valor_lido', 'limite_configurado_snapshot', 'data_resolucao',
]


def _serializar_evento(cliente, evento):
    sensor = odoo_cliente.executar(
        cliente, 'sensor_monitor.sensor', 'read', [evento['sensor_id'][0]], fields=['sensor_code'],
    )[0]
    area = odoo_cliente.executar(
        cliente, 'sensor_monitor.area', 'read', [evento['area_id'][0]], fields=['area_code', 'name'],
    )[0]
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
    return [_serializar_evento(cliente, e) for e in eventos]
