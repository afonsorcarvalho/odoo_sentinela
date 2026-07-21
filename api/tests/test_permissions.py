from api.odoo import ODOO_DB, ODOO_URL, get_cliente_servico
from api.permissions import obter_sites_permitidos
from api.tests.tenant_fixtures import criar_tenant, remover_tenant
from ingestao import odoo_cliente


def test_servico_admin_ve_todos_os_sites():
    # admin de serviço não é filtrado por tenant: vê os sites de todos.
    tenant_a = criar_tenant('PERM-ADMIN-A')
    tenant_b = criar_tenant('PERM-ADMIN-B')
    try:
        cliente = get_cliente_servico()
        sites = obter_sites_permitidos(cliente)
        assert tenant_a['site_code'] in sites
        assert tenant_b['site_code'] in sites
    finally:
        remover_tenant(tenant_a)
        remover_tenant(tenant_b)


def test_usuario_tenant_ve_apenas_o_proprio_site():
    tenant_a = criar_tenant('PERM-A')
    tenant_b = criar_tenant('PERM-B')
    try:
        cliente_a = odoo_cliente.conectar(ODOO_URL, ODOO_DB, tenant_a['login'], tenant_a['senha'])
        sites = obter_sites_permitidos(cliente_a)
        assert sites == [tenant_a['site_code']]
        assert tenant_b['site_code'] not in sites
    finally:
        remover_tenant(tenant_a)
        remover_tenant(tenant_b)
