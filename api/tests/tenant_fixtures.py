from api.odoo import get_cliente_servico
from ingestao import odoo_cliente

_SENHA_PADRAO = 'senha-teste-tenant-123'


def criar_tenant(sufixo):
    cliente = get_cliente_servico()
    # Rastrear IDs criados para limpeza auto em caso de falha
    ids_criados = {}

    try:
        # Ordem de criação: partner → site → hub → coletor → area → sensor → user
        partner_id = odoo_cliente.executar(
            cliente, 'res.partner', 'create', {'name': f'Cliente Teste {sufixo}'},
        )
        ids_criados['partner_id'] = partner_id

        site_code = f'SITE-TENANT-{sufixo}'
        site_id = odoo_cliente.executar(
            cliente, 'sensor_monitor.site', 'create', {
                'name': f'Site Teste {sufixo}', 'partner_id': partner_id,
                'site_code': site_code, 'vertical': 'cme_hospitalar',
            },
        )
        ids_criados['site_id'] = site_id

        hub_id = odoo_cliente.executar(
            cliente, 'sensor_monitor.hub', 'create', {
                'name': f'Hub Teste {sufixo}', 'site_id': site_id, 'hub_code': f'HUB-TENANT-{sufixo}',
            },
        )
        ids_criados['hub_id'] = hub_id

        coletor_id = odoo_cliente.executar(
            cliente, 'sensor_monitor.coletor', 'create', {
                'name': f'Coletor Teste {sufixo}', 'hub_id': hub_id,
                'coletor_code': f'COL-TENANT-{sufixo}', 'tipo': 'esp32_wifi',
            },
        )
        ids_criados['coletor_id'] = coletor_id

        categoria_id = odoo_cliente.executar(cliente, 'sensor_monitor.area.category', 'search', [], limit=1)[0]
        area_id = odoo_cliente.executar(
            cliente, 'sensor_monitor.area', 'create', {
                'name': f'Área Teste {sufixo}', 'site_id': site_id,
                'area_category_id': categoria_id, 'area_code': f'AREA-TENANT-{sufixo}',
            },
        )
        ids_criados['area_id'] = area_id

        tipo_medida_id = odoo_cliente.executar(cliente, 'sensor_monitor.measurement.type', 'search', [], limit=1)[0]
        sensor_code = f'SNR-TENANT-{sufixo}'
        sensor_id = odoo_cliente.executar(
            cliente, 'sensor_monitor.sensor', 'create', {
                'name': f'Sensor Teste {sufixo}', 'sensor_code': sensor_code,
                'coletor_id': coletor_id, 'area_id': area_id, 'measurement_type_id': tipo_medida_id,
                'protocolo_origem': '4-20ma',
            },
        )
        ids_criados['sensor_id'] = sensor_id

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
        ids_criados['user_id'] = user_id

        return {
            'partner_id': partner_id, 'site_id': site_id, 'site_code': site_code,
            'hub_id': hub_id, 'coletor_id': coletor_id, 'area_id': area_id,
            'sensor_id': sensor_id, 'sensor_code': sensor_code,
            'user_id': user_id, 'login': login, 'senha': _SENHA_PADRAO,
        }
    except Exception:
        # Limpeza best-effort em ordem reversa (filho-antes-pai): user → sensor → area → coletor → hub → site → partner
        if 'user_id' in ids_criados:
            try:
                odoo_cliente.executar(cliente, 'res.users', 'unlink', [ids_criados['user_id']])
            except Exception:
                pass
        if 'sensor_id' in ids_criados:
            try:
                odoo_cliente.executar(cliente, 'sensor_monitor.sensor', 'unlink', [ids_criados['sensor_id']])
            except Exception:
                pass
        if 'area_id' in ids_criados:
            try:
                odoo_cliente.executar(cliente, 'sensor_monitor.area', 'unlink', [ids_criados['area_id']])
            except Exception:
                pass
        if 'coletor_id' in ids_criados:
            try:
                odoo_cliente.executar(cliente, 'sensor_monitor.coletor', 'unlink', [ids_criados['coletor_id']])
            except Exception:
                pass
        if 'hub_id' in ids_criados:
            try:
                odoo_cliente.executar(cliente, 'sensor_monitor.hub', 'unlink', [ids_criados['hub_id']])
            except Exception:
                pass
        if 'site_id' in ids_criados:
            try:
                odoo_cliente.executar(cliente, 'sensor_monitor.site', 'unlink', [ids_criados['site_id']])
            except Exception:
                pass
        if 'partner_id' in ids_criados:
            try:
                odoo_cliente.executar(cliente, 'res.partner', 'unlink', [ids_criados['partner_id']])
            except Exception:
                pass
        raise


def remover_tenant(dados):
    cliente = get_cliente_servico()
    odoo_cliente.executar(cliente, 'res.users', 'unlink', [dados['user_id']])
    odoo_cliente.executar(cliente, 'sensor_monitor.sensor', 'unlink', [dados['sensor_id']])
    odoo_cliente.executar(cliente, 'sensor_monitor.area', 'unlink', [dados['area_id']])
    odoo_cliente.executar(cliente, 'sensor_monitor.coletor', 'unlink', [dados['coletor_id']])
    odoo_cliente.executar(cliente, 'sensor_monitor.hub', 'unlink', [dados['hub_id']])
    odoo_cliente.executar(cliente, 'sensor_monitor.site', 'unlink', [dados['site_id']])
    odoo_cliente.executar(cliente, 'res.partner', 'unlink', [dados['partner_id']])
