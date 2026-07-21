from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from api.main import app
from api.odoo import get_cliente_servico
from api.tests.tenant_fixtures import criar_tenant, remover_tenant
from ingestao import odoo_cliente

client = TestClient(app)


def _headers():
    resposta = client.post('/auth/login', json={'usuario': 'admin', 'senha': 'admin'})
    token = resposta.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def _criar_evento(cliente, sensor_code, **overrides):
    sensor_ids = odoo_cliente.executar(
        cliente, 'sensor_monitor.sensor', 'search', [('sensor_code', '=', sensor_code)],
    )
    sensor = odoo_cliente.executar(
        cliente, 'sensor_monitor.sensor', 'read', [sensor_ids[0]], fields=['area_id'],
    )[0]
    valores = {
        'sensor_id': sensor_ids[0],
        'area_id': sensor['area_id'][0],
        'timestamp_deteccao': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
        'valor_lido': 99.9,
        'tipo_violacao': 'acima_limite',
        'limite_configurado_snapshot': 30.0,
        'status': 'aberto',
    }
    valores.update(overrides)
    return odoo_cliente.executar(cliente, 'sensor_monitor.alarm.event', 'create', valores)


def _apagar(cliente, *ids):
    if ids:
        odoo_cliente.executar(cliente, 'sensor_monitor.alarm.event', 'unlink', list(ids))


def test_listar_alarmes_sem_token_retorna_401():
    resposta = client.get('/alarmes')
    assert resposta.status_code == 401


def test_listar_alarmes_com_token_inclui_evento_criado():
    cliente = get_cliente_servico()
    evento_id = _criar_evento(cliente, 'SNR-SIM-TEMP-01')
    try:
        resposta = client.get('/alarmes', headers=_headers())
        assert resposta.status_code == 200
        corpo = resposta.json()
        evento = next(e for e in corpo if e['id'] == evento_id)
        assert evento['sensor_code'] == 'SNR-SIM-TEMP-01'
        assert evento['area_code']
        assert evento['status'] == 'aberto'
        assert evento['tipo_violacao'] == 'acima_limite'
        assert isinstance(evento['timestamp_deteccao'], int)
    finally:
        _apagar(cliente, evento_id)


def test_listar_alarmes_ordenado_por_timestamp_desc():
    cliente = get_cliente_servico()
    id1 = _criar_evento(cliente, 'SNR-SIM-TEMP-01')
    id2 = _criar_evento(cliente, 'SNR-SIM-PRES-01')
    try:
        resposta = client.get('/alarmes', headers=_headers())
        timestamps = [e['timestamp_deteccao'] for e in resposta.json()]
        assert timestamps == sorted(timestamps, reverse=True)
    finally:
        _apagar(cliente, id1, id2)


def test_listar_alarmes_filtra_por_status():
    cliente = get_cliente_servico()
    aberto_id = _criar_evento(cliente, 'SNR-SIM-TEMP-01', status='aberto')
    resolvido_id = _criar_evento(cliente, 'SNR-SIM-TEMP-01', status='resolvido')
    try:
        resposta = client.get('/alarmes', params={'status': 'resolvido'}, headers=_headers())
        ids = {e['id'] for e in resposta.json()}
        assert resolvido_id in ids
        assert aberto_id not in ids
    finally:
        _apagar(cliente, aberto_id, resolvido_id)


def test_listar_alarmes_filtra_por_sensor_code():
    cliente = get_cliente_servico()
    id_temp = _criar_evento(cliente, 'SNR-SIM-TEMP-01')
    id_pres = _criar_evento(cliente, 'SNR-SIM-PRES-01')
    try:
        resposta = client.get('/alarmes', params={'sensor_code': 'SNR-SIM-PRES-01'}, headers=_headers())
        ids = {e['id'] for e in resposta.json()}
        assert id_pres in ids
        assert id_temp not in ids
    finally:
        _apagar(cliente, id_temp, id_pres)


def test_listar_alarmes_sensor_code_inexistente_retorna_404():
    resposta = client.get('/alarmes', params={'sensor_code': 'SNR-NAO-EXISTE-XYZ'}, headers=_headers())
    assert resposta.status_code == 404


def test_listar_alarmes_filtra_por_area_code():
    cliente = get_cliente_servico()
    id_temp = _criar_evento(cliente, 'SNR-SIM-TEMP-01')
    try:
        resposta_evento = client.get('/alarmes', params={'sensor_code': 'SNR-SIM-TEMP-01'}, headers=_headers())
        area_code = resposta_evento.json()[0]['area_code']

        resposta = client.get('/alarmes', params={'area_code': area_code}, headers=_headers())
        ids = {e['id'] for e in resposta.json()}
        assert id_temp in ids
    finally:
        _apagar(cliente, id_temp)


def test_listar_alarmes_area_code_inexistente_retorna_lista_vazia():
    resposta = client.get('/alarmes', params={'area_code': 'AREA-NAO-EXISTE-XYZ'}, headers=_headers())
    assert resposta.status_code == 200
    assert resposta.json() == []


def test_listar_alarmes_filtra_por_desde_e_ate():
    cliente = get_cliente_servico()
    agora = datetime.now(timezone.utc)
    antigo_id = _criar_evento(
        cliente, 'SNR-SIM-TEMP-01',
        timestamp_deteccao=(agora - timedelta(days=10)).strftime('%Y-%m-%d %H:%M:%S'),
    )
    recente_id = _criar_evento(
        cliente, 'SNR-SIM-TEMP-01',
        timestamp_deteccao=agora.strftime('%Y-%m-%d %H:%M:%S'),
    )
    try:
        desde = (agora - timedelta(days=1)).isoformat()
        resposta = client.get('/alarmes', params={'desde': desde}, headers=_headers())
        ids = {e['id'] for e in resposta.json()}
        assert recente_id in ids
        assert antigo_id not in ids
    finally:
        _apagar(cliente, antigo_id, recente_id)


def test_listar_alarmes_campos_nulos_aparecem_como_null():
    cliente = get_cliente_servico()
    evento_id = _criar_evento(cliente, 'SNR-SIM-TEMP-01')
    try:
        resposta = client.get('/alarmes', headers=_headers())
        evento = next(e for e in resposta.json() if e['id'] == evento_id)
        assert evento['timestamp_resolucao_sensor'] is None
        assert evento['data_resolucao'] is None
        assert evento['observacoes'] is None
        assert evento['usuario_responsavel'] is None
    finally:
        _apagar(cliente, evento_id)


def test_listar_alarmes_nao_inclui_evento_de_outro_tenant():
    cliente_servico = get_cliente_servico()
    tenant_a = tenant_b = None
    evento_b_id = None
    try:
        tenant_a = criar_tenant('ALARM-A')
        tenant_b = criar_tenant('ALARM-B')
        evento_b_id = _criar_evento(cliente_servico, tenant_b['sensor_code'])
        resposta_login = client.post('/auth/login', json={'usuario': tenant_a['login'], 'senha': tenant_a['senha']})
        token = resposta_login.json()['access_token']
        resposta = client.get('/alarmes', headers={'Authorization': f'Bearer {token}'})
        ids = {e['id'] for e in resposta.json()}
        assert evento_b_id not in ids
    finally:
        if evento_b_id is not None:
            _apagar(cliente_servico, evento_b_id)
        if tenant_a is not None:
            remover_tenant(tenant_a)
        if tenant_b is not None:
            remover_tenant(tenant_b)
