from datetime import datetime, timezone

from fastapi.testclient import TestClient

from api.main import app
from api.odoo import get_cliente_servico
from ingestao import odoo_cliente

client = TestClient(app)


def _headers():
    resposta = client.post('/auth/login', json={'usuario': 'admin', 'senha': 'admin'})
    token = resposta.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def _criar_evento(cliente, sensor_code, status='aberto'):
    sensor_ids = odoo_cliente.executar(
        cliente, 'sensor_monitor.sensor', 'search', [('sensor_code', '=', sensor_code)],
    )
    sensor = odoo_cliente.executar(
        cliente, 'sensor_monitor.sensor', 'read', [sensor_ids[0]], fields=['area_id'],
    )[0]
    return odoo_cliente.executar(
        cliente, 'sensor_monitor.alarm.event', 'create', {
            'sensor_id': sensor_ids[0],
            'area_id': sensor['area_id'][0],
            'timestamp_deteccao': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            'valor_lido': 99.9,
            'tipo_violacao': 'acima_limite',
            'limite_configurado_snapshot': 30.0,
            'status': status,
        },
    )


def test_listar_alarmes_sem_token_retorna_401():
    resposta = client.get('/alarmes')
    assert resposta.status_code == 401


def test_listar_alarmes_com_token_inclui_evento_criado():
    cliente = get_cliente_servico()
    _criar_evento(cliente, 'SNR-SIM-TEMP-01')

    resposta = client.get('/alarmes', headers=_headers())
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert len(corpo) > 0
    evento = corpo[0]
    assert evento['sensor_code'] == 'SNR-SIM-TEMP-01'
    assert evento['area']['area_code']
    assert evento['status'] == 'aberto'
    assert evento['tipo_violacao'] == 'acima_limite'


def test_listar_alarmes_ordenado_por_timestamp_desc():
    cliente = get_cliente_servico()
    _criar_evento(cliente, 'SNR-SIM-TEMP-01')
    _criar_evento(cliente, 'SNR-SIM-PRES-01')

    resposta = client.get('/alarmes', headers=_headers())
    timestamps = [e['timestamp_deteccao'] for e in resposta.json()]
    assert timestamps == sorted(timestamps, reverse=True)
