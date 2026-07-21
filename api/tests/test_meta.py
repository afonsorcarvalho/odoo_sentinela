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


from api.tests.tenant_fixtures import criar_tenant, remover_tenant


def _headers_para(login, senha):
    resposta = client.post('/auth/login', json={'usuario': login, 'senha': senha})
    token = resposta.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def test_obter_sensor_de_outro_tenant_retorna_404():
    tenant_a = tenant_b = None
    try:
        tenant_a = criar_tenant('META-A')
        tenant_b = criar_tenant('META-B')
        resposta = client.get(
            f"/sensores/{tenant_b['sensor_code']}",
            headers=_headers_para(tenant_a['login'], tenant_a['senha']),
        )
        assert resposta.status_code == 404
    finally:
        if tenant_a is not None:
            remover_tenant(tenant_a)
        if tenant_b is not None:
            remover_tenant(tenant_b)


def test_listar_sensores_nao_inclui_sensor_de_outro_tenant():
    tenant_a = tenant_b = None
    try:
        tenant_a = criar_tenant('META-LIST-A')
        tenant_b = criar_tenant('META-LIST-B')
        resposta = client.get('/sensores', headers=_headers_para(tenant_a['login'], tenant_a['senha']))
        codigos = [s['sensor_code'] for s in resposta.json()]
        assert tenant_a['sensor_code'] in codigos
        assert tenant_b['sensor_code'] not in codigos
    finally:
        if tenant_a is not None:
            remover_tenant(tenant_a)
        if tenant_b is not None:
            remover_tenant(tenant_b)
