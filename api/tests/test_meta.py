from fastapi.testclient import TestClient

from api.main import app
from api.odoo import get_cliente_servico
from ingestao import odoo_cliente

client = TestClient(app)


def _headers():
    resposta = client.post('/auth/login', json={'usuario': 'admin', 'senha': 'admin'})
    token = resposta.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def test_listar_sensores_sem_token_retorna_401():
    resposta = client.get('/sensores')
    assert resposta.status_code == 401


def test_listar_sensores_com_token_retorna_lista():
    resposta = client.get('/sensores', headers=_headers())
    assert resposta.status_code == 200
    codigos = [s['sensor_code'] for s in resposta.json()]
    assert 'TEMP-01' in codigos
    assert 'SNR-SIM-TEMP-01' in codigos


def test_obter_sensor_existente_bate_shape():
    resposta = client.get('/sensores/SNR-SIM-TEMP-01', headers=_headers())
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo['sensor_code'] == 'SNR-SIM-TEMP-01'
    assert corpo['protocolo_origem'] == '4-20ma'
    assert corpo['measurement_type']['code'] == 'temperatura'
    assert corpo['area']['category'] == 'Expurgo'


def test_obter_sensor_inexistente_retorna_404():
    resposta = client.get('/sensores/SNR-NAO-EXISTE-XYZ', headers=_headers())
    assert resposta.status_code == 404


def test_threshold_sensor_sem_limiar_retorna_null():
    resposta = client.get('/sensores/SNR-SIM-TEMP-01/threshold', headers=_headers())
    assert resposta.status_code == 200
    assert resposta.json() is None


def test_threshold_sensor_com_limiar_retorna_valores():
    cliente = get_cliente_servico()
    sensor_ids = odoo_cliente.executar(
        cliente, 'sensor_monitor.sensor', 'search', [('sensor_code', '=', 'SNR-SIM-PRES-01')],
    )
    threshold_id = odoo_cliente.executar(
        cliente, 'sensor_monitor.alarm.threshold', 'create',
        {'sensor_id': sensor_ids[0], 'limite_min': -10.0, 'limite_max': -2.5, 'is_valor_padrao_regulatorio': True},
    )
    try:
        resposta = client.get('/sensores/SNR-SIM-PRES-01/threshold', headers=_headers())
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo['sensor_id'] == 'SNR-SIM-PRES-01'
        assert corpo['limite_min'] == -10.0
        assert corpo['limite_max'] == -2.5
        assert corpo['is_valor_padrao_regulatorio'] is True
    finally:
        odoo_cliente.executar(cliente, 'sensor_monitor.alarm.threshold', 'unlink', [threshold_id])


def test_threshold_sensor_inexistente_retorna_404():
    resposta = client.get('/sensores/SNR-NAO-EXISTE-XYZ/threshold', headers=_headers())
    assert resposta.status_code == 404
