from fastapi.testclient import TestClient

from api.main import app
from api.odoo import SITE_CODE, get_cliente_servico
from ingestao import odoo_cliente

client = TestClient(app)


def _headers():
    resposta = client.post('/auth/login', json={'usuario': 'admin', 'senha': 'admin'})
    token = resposta.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def _site_id(cliente):
    sites = odoo_cliente.executar(
        cliente, 'sensor_monitor.site', 'search_read',
        [('site_code', '=', SITE_CODE)], fields=['id'],
    )
    if sites:
        return sites[0]['id']
    partner_ids = odoo_cliente.executar(cliente, 'res.partner', 'search', [], limit=1)
    return odoo_cliente.executar(
        cliente, 'sensor_monitor.site', 'create',
        {
            'name': 'Site de teste config',
            'partner_id': partner_ids[0],
            'site_code': SITE_CODE,
            'vertical': 'cme_hospitalar',
        },
    )


def test_config_sem_token_retorna_401():
    resposta = client.get('/config')
    assert resposta.status_code == 401


def test_config_sem_registro_retorna_default():
    cliente = get_cliente_servico()
    site_id = _site_id(cliente)
    configs_existentes = odoo_cliente.executar(
        cliente, 'sensor_monitor.dashboard.config', 'search_read',
        [('site_id', '=', site_id)], fields=['site_id', 'carousel_interval_ms'],
    )
    if configs_existentes:
        odoo_cliente.executar(
            cliente, 'sensor_monitor.dashboard.config', 'unlink',
            [c['id'] for c in configs_existentes],
        )

    try:
        resposta = client.get('/config', headers=_headers())

        assert resposta.status_code == 200
        assert resposta.json() == {'carousel_interval_ms': 3000}
    finally:
        for c in configs_existentes:
            odoo_cliente.executar(
                cliente, 'sensor_monitor.dashboard.config', 'create',
                {
                    'site_id': c['site_id'][0] if isinstance(c['site_id'], list) else c['site_id'],
                    'carousel_interval_ms': c['carousel_interval_ms'],
                },
            )


def test_config_com_registro_retorna_valor_configurado():
    cliente = get_cliente_servico()
    site_id = _site_id(cliente)
    config_id = odoo_cliente.executar(
        cliente, 'sensor_monitor.dashboard.config', 'create',
        {'site_id': site_id, 'carousel_interval_ms': 7000},
    )
    try:
        resposta = client.get('/config', headers=_headers())
        assert resposta.status_code == 200
        assert resposta.json() == {'carousel_interval_ms': 7000}
    finally:
        odoo_cliente.executar(cliente, 'sensor_monitor.dashboard.config', 'unlink', [config_id])
