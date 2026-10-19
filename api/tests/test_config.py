import json
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


def _limpar_config(cliente, site_id):
    """Remove config de dashboard do site (unique(site_id)) — evita colisão
    com estado deixado por testes anteriores antes de um create direto."""
    existentes = odoo_cliente.executar(
        cliente, 'sensor_monitor.dashboard.config', 'search',
        [('site_id', '=', site_id)],
    )
    if existentes:
        odoo_cliente.executar(
            cliente, 'sensor_monitor.dashboard.config', 'unlink', existentes,
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
        assert resposta.json() == {
            'carousel_interval_ms': 3000,
            'carousel_transition_ms': 300,
            'layout': None,
        }
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
    _limpar_config(cliente, site_id)
    config_id = odoo_cliente.executar(
        cliente, 'sensor_monitor.dashboard.config', 'create',
        {'site_id': site_id, 'carousel_interval_ms': 7000, 'carousel_transition_ms': 600},
    )
    try:
        resposta = client.get('/config', headers=_headers())
        assert resposta.status_code == 200
        assert resposta.json() == {
            'carousel_interval_ms': 7000,
            'carousel_transition_ms': 600,
            'layout': None,
        }
    finally:
        odoo_cliente.executar(cliente, 'sensor_monitor.dashboard.config', 'unlink', [config_id])


def test_config_retorna_layout_quando_salvo():
    cliente = get_cliente_servico()
    site_id = _site_id(cliente)
    layout = {'version': 1, 'grid': {'cols': 12, 'rowHeight': 40, 'margin': [8, 8]}, 'widgets': []}
    import json as _json
    _limpar_config(cliente, site_id)
    config_id = odoo_cliente.executar(
        cliente, 'sensor_monitor.dashboard.config', 'create',
        {'site_id': site_id, 'layout_json': _json.dumps(layout)},
    )
    try:
        resposta = client.get('/config', headers=_headers())
        assert resposta.status_code == 200
        assert resposta.json()['layout'] == layout
    finally:
        odoo_cliente.executar(cliente, 'sensor_monitor.dashboard.config', 'unlink', [config_id])


def test_config_layout_none_quando_ausente():
    cliente = get_cliente_servico()
    site_id = _site_id(cliente)
    existentes = odoo_cliente.executar(
        cliente, 'sensor_monitor.dashboard.config', 'search',
        [('site_id', '=', site_id)],
    )
    if existentes:
        odoo_cliente.executar(cliente, 'sensor_monitor.dashboard.config', 'unlink', existentes)
    resposta = client.get('/config', headers=_headers())
    assert resposta.status_code == 200
    assert resposta.json()['layout'] is None


def test_put_layout_admin_faz_upsert():
    cliente = get_cliente_servico()
    site_id = _site_id(cliente)
    existentes = odoo_cliente.executar(
        cliente, 'sensor_monitor.dashboard.config', 'search',
        [('site_id', '=', site_id)],
    )
    if existentes:
        odoo_cliente.executar(cliente, 'sensor_monitor.dashboard.config', 'unlink', existentes)
    layout = {'version': 1, 'grid': {'cols': 12, 'rowHeight': 40, 'margin': [8, 8]},
              'widgets': [{'id': 'w1', 'type': 'kpi', 'layout': {'x': 0, 'y': 0, 'w': 2, 'h': 2},
                           'binding': {'sensorCode': 'PRESS-EXP-01'}, 'options': {}}]}
    try:
        resposta = client.put('/config/layout', json={'layout': layout}, headers=_headers())
        assert resposta.status_code == 200
        assert resposta.json()['layout'] == layout
        get_resp = client.get('/config', headers=_headers())
        assert get_resp.json()['layout'] == layout
    finally:
        atuais = odoo_cliente.executar(
            cliente, 'sensor_monitor.dashboard.config', 'search',
            [('site_id', '=', site_id)],
        )
        if atuais:
            odoo_cliente.executar(cliente, 'sensor_monitor.dashboard.config', 'unlink', atuais)


def test_put_layout_atualiza_existente_sem_duplicar():
    cliente = get_cliente_servico()
    site_id = _site_id(cliente)
    existentes = odoo_cliente.executar(
        cliente, 'sensor_monitor.dashboard.config', 'search',
        [('site_id', '=', site_id)],
    )
    if existentes:
        odoo_cliente.executar(cliente, 'sensor_monitor.dashboard.config', 'unlink', existentes)
    layout_1 = {'version': 1, 'grid': {'cols': 12, 'rowHeight': 40, 'margin': [8, 8]}, 'widgets': []}
    layout_2 = {'version': 2, 'grid': {'cols': 12, 'rowHeight': 40, 'margin': [8, 8]},
                'widgets': [{'id': 'w1', 'type': 'kpi', 'layout': {'x': 0, 'y': 0, 'w': 2, 'h': 2},
                             'binding': {'sensorCode': 'PRESS-EXP-01'}, 'options': {}}]}
    try:
        primeira = client.put('/config/layout', json={'layout': layout_1}, headers=_headers())
        assert primeira.status_code == 200

        segunda = client.put('/config/layout', json={'layout': layout_2}, headers=_headers())
        assert segunda.status_code == 200
        assert segunda.json()['layout'] == layout_2

        get_resp = client.get('/config', headers=_headers())
        assert get_resp.json()['layout'] == layout_2

        atuais = odoo_cliente.executar(
            cliente, 'sensor_monitor.dashboard.config', 'search',
            [('site_id', '=', site_id)],
        )
        assert len(atuais) == 1
    finally:
        atuais = odoo_cliente.executar(
            cliente, 'sensor_monitor.dashboard.config', 'search',
            [('site_id', '=', site_id)],
        )
        if atuais:
            odoo_cliente.executar(cliente, 'sensor_monitor.dashboard.config', 'unlink', atuais)


def test_put_layout_sem_token_401():
    resposta = client.put('/config/layout', json={'layout': {'version': 1, 'widgets': []}})
    assert resposta.status_code == 401


def test_put_layout_body_malformado_422_ou_400():
    resposta = client.put('/config/layout', json={'layout': {'version': 1}}, headers=_headers())
    assert resposta.status_code in (400, 422)


def _login_tenant(dados):
    resposta = client.post('/auth/login', json={'usuario': dados['login'], 'senha': dados['senha']})
    assert resposta.status_code == 200
    return {'Authorization': f"Bearer {resposta.json()['access_token']}"}


def test_config_de_usuario_tenant_vem_do_site_dele_nao_do_site_code_fixo():
    from api.tests.tenant_fixtures import criar_tenant, remover_tenant

    servico = get_cliente_servico()
    # Site "padrão" do processo (SITE_CODE) com layout que o tenant NÃO pode ver.
    site_padrao = _site_id(servico)
    _limpar_config(servico, site_padrao)
    layout_alheio = {'version': 1, 'grid': {}, 'widgets': [{'id': 'alheio'}]}
    cfg_padrao = odoo_cliente.executar(
        servico, 'sensor_monitor.dashboard.config', 'create',
        {'site_id': site_padrao, 'layout_json': json.dumps(layout_alheio)},
    )
    tenant = criar_tenant('CFG1')
    cfg_tenant = odoo_cliente.executar(
        servico, 'sensor_monitor.dashboard.config', 'create',
        {'site_id': tenant['site_id'], 'carousel_interval_ms': 9100,
         'layout_json': json.dumps({'version': 1, 'grid': {}, 'widgets': []})},
    )
    try:
        resposta = client.get('/config', headers=_login_tenant(tenant))
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo['carousel_interval_ms'] == 9100
        assert corpo['layout']['widgets'] == []
    finally:
        odoo_cliente.executar(servico, 'sensor_monitor.dashboard.config', 'unlink', [cfg_padrao, cfg_tenant])
        remover_tenant(tenant)


def test_config_param_site_de_outro_tenant_retorna_404():
    from api.tests.tenant_fixtures import criar_tenant, remover_tenant

    tenant = criar_tenant('CFG2')
    try:
        resposta = client.get(f'/config?site={SITE_CODE}', headers=_login_tenant(tenant))
        assert resposta.status_code == 404
    finally:
        remover_tenant(tenant)
