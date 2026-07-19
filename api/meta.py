from fastapi import APIRouter, Depends, HTTPException

from ingestao import odoo_cliente

from .auth import verificar_token
from .odoo import get_cliente_servico

router = APIRouter()

_CAMPOS_SENSOR = ['sensor_code', 'name', 'unidade', 'protocolo_origem', 'area_id', 'measurement_type_id']


def _serializar_sensor(cliente, sensor):
    area = odoo_cliente.executar(
        cliente, 'sensor_monitor.area', 'read', [sensor['area_id'][0]],
        fields=['area_code', 'name', 'area_category_id'],
    )[0]
    categoria = odoo_cliente.executar(
        cliente, 'sensor_monitor.area.category', 'read', [area['area_category_id'][0]], fields=['name'],
    )[0]
    tipo_medida = odoo_cliente.executar(
        cliente, 'sensor_monitor.measurement.type', 'read', [sensor['measurement_type_id'][0]],
        fields=['code', 'name', 'unidade_padrao'],
    )[0]
    return {
        'sensor_code': sensor['sensor_code'],
        'name': sensor['name'],
        'unidade': sensor['unidade'] or tipo_medida['unidade_padrao'],
        'protocolo_origem': sensor['protocolo_origem'],
        'measurement_type': {'code': tipo_medida['code'], 'name': tipo_medida['name']},
        'area': {'area_code': area['area_code'], 'name': area['name'], 'category': categoria['name']},
    }


def listar_sensores(cliente):
    sensores = odoo_cliente.executar(cliente, 'sensor_monitor.sensor', 'search_read', [], fields=_CAMPOS_SENSOR)
    return [_serializar_sensor(cliente, s) for s in sensores]


def obter_sensor(cliente, sensor_code):
    sensores = odoo_cliente.executar(
        cliente, 'sensor_monitor.sensor', 'search_read',
        [('sensor_code', '=', sensor_code)], fields=_CAMPOS_SENSOR,
    )
    if not sensores:
        return None
    return _serializar_sensor(cliente, sensores[0])


def obter_threshold(cliente, sensor_code):
    sensor_ids = odoo_cliente.executar(
        cliente, 'sensor_monitor.sensor', 'search', [('sensor_code', '=', sensor_code)],
    )
    if not sensor_ids:
        raise ValueError(f"sensor '{sensor_code}' não encontrado")
    thresholds = odoo_cliente.executar(
        cliente, 'sensor_monitor.alarm.threshold', 'search_read',
        [('sensor_id', '=', sensor_ids[0])],
        fields=['limite_min', 'limite_max', 'is_valor_padrao_regulatorio'],
    )
    if not thresholds:
        return None
    t = thresholds[0]
    return {
        'sensor_id': sensor_code,
        'limite_min': t['limite_min'],
        'limite_max': t['limite_max'],
        'is_valor_padrao_regulatorio': t['is_valor_padrao_regulatorio'],
    }


@router.get('/sensores')
def get_sensores(cliente=Depends(get_cliente_servico), _claims=Depends(verificar_token)):
    return listar_sensores(cliente)


@router.get('/sensores/{sensor_code}')
def get_sensor(sensor_code: str, cliente=Depends(get_cliente_servico), _claims=Depends(verificar_token)):
    resultado = obter_sensor(cliente, sensor_code)
    if resultado is None:
        raise HTTPException(status_code=404, detail=f"sensor '{sensor_code}' não encontrado")
    return resultado


@router.get('/sensores/{sensor_code}/threshold')
def get_threshold(sensor_code: str, cliente=Depends(get_cliente_servico), _claims=Depends(verificar_token)):
    try:
        return obter_threshold(cliente, sensor_code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
