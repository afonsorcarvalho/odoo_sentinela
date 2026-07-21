from api.odoo import get_cliente_servico
from ingestao import odoo_cliente

_SENHA_PADRAO = 'senha-teste-tenant-123'


def criar_tenant(sufixo):
    cliente = get_cliente_servico()

    partner_id = odoo_cliente.executar(
        cliente, 'res.partner', 'create', {'name': f'Cliente Teste {sufixo}'},
    )
    site_code = f'SITE-TENANT-{sufixo}'
    site_id = odoo_cliente.executar(
        cliente, 'sensor_monitor.site', 'create', {
            'name': f'Site Teste {sufixo}', 'partner_id': partner_id,
            'site_code': site_code, 'vertical': 'cme_hospitalar',
        },
    )
    hub_id = odoo_cliente.executar(
        cliente, 'sensor_monitor.hub', 'create', {
            'name': f'Hub Teste {sufixo}', 'site_id': site_id, 'hub_code': f'HUB-TENANT-{sufixo}',
        },
    )
    coletor_id = odoo_cliente.executar(
        cliente, 'sensor_monitor.coletor', 'create', {
            'name': f'Coletor Teste {sufixo}', 'hub_id': hub_id,
            'coletor_code': f'COL-TENANT-{sufixo}', 'tipo': 'esp32_wifi',
        },
    )
    categoria_id = odoo_cliente.executar(cliente, 'sensor_monitor.area.category', 'search', [], limit=1)[0]
    area_id = odoo_cliente.executar(
        cliente, 'sensor_monitor.area', 'create', {
            'name': f'Área Teste {sufixo}', 'site_id': site_id,
            'area_category_id': categoria_id, 'area_code': f'AREA-TENANT-{sufixo}',
        },
    )
    tipo_medida_id = odoo_cliente.executar(cliente, 'sensor_monitor.measurement.type', 'search', [], limit=1)[0]
    sensor_code = f'SNR-TENANT-{sufixo}'
    sensor_id = odoo_cliente.executar(
        cliente, 'sensor_monitor.sensor', 'create', {
            'name': f'Sensor Teste {sufixo}', 'sensor_code': sensor_code,
            'coletor_id': coletor_id, 'area_id': area_id, 'measurement_type_id': tipo_medida_id,
            'protocolo_origem': '4-20ma',
        },
    )
    view_group_id = odoo_cliente.executar(
        cliente, 'ir.model.data', 'search_read',
        [('module', '=', 'afr_sentinela_sensor_monitor'), ('name', '=', 'group_sensor_monitor_view')],
        fields=['res_id'], limit=1,
    )[0]['res_id']
    base_user_group_id = odoo_cliente.executar(
        cliente, 'ir.model.data', 'search_read',
        [('module', '=', 'base'), ('name', '=', 'group_user')], fields=['res_id'], limit=1,
    )[0]['res_id']
    login = f'usuario.tenant.{sufixo}@teste.com'.lower()
    user_id = odoo_cliente.executar(
        cliente, 'res.users', 'create', {
            'name': f'Usuário Tenant {sufixo}', 'login': login, 'password': _SENHA_PADRAO,
            'partner_id': partner_id, 'groups_id': [(6, 0, [view_group_id, base_user_group_id])],
        },
    )
    return {
        'partner_id': partner_id, 'site_id': site_id, 'site_code': site_code,
        'hub_id': hub_id, 'coletor_id': coletor_id, 'area_id': area_id,
        'sensor_id': sensor_id, 'sensor_code': sensor_code,
        'user_id': user_id, 'login': login, 'senha': _SENHA_PADRAO,
    }


def remover_tenant(dados):
    cliente = get_cliente_servico()
    odoo_cliente.executar(cliente, 'res.users', 'unlink', [dados['user_id']])
    odoo_cliente.executar(cliente, 'sensor_monitor.sensor', 'unlink', [dados['sensor_id']])
    odoo_cliente.executar(cliente, 'sensor_monitor.area', 'unlink', [dados['area_id']])
    odoo_cliente.executar(cliente, 'sensor_monitor.coletor', 'unlink', [dados['coletor_id']])
    odoo_cliente.executar(cliente, 'sensor_monitor.hub', 'unlink', [dados['hub_id']])
    odoo_cliente.executar(cliente, 'sensor_monitor.site', 'unlink', [dados['site_id']])
    odoo_cliente.executar(cliente, 'res.partner', 'unlink', [dados['partner_id']])
