from ingestao import odoo_cliente, provisionar_odoo_sim

ODOO_URL = 'http://localhost:8189'
ODOO_DB = 'sentinela'
ODOO_USUARIO = 'admin'
ODOO_SENHA = 'admin'


def _cliente():
    return odoo_cliente.conectar(ODOO_URL, ODOO_DB, ODOO_USUARIO, ODOO_SENHA)


def test_provisionar_e_idempotente():
    cliente = _cliente()
    resultado1 = provisionar_odoo_sim.provisionar(cliente)
    resultado2 = provisionar_odoo_sim.provisionar(cliente)
    assert resultado1 == resultado2


def test_resolver_coletor_apos_provisionar():
    cliente = _cliente()
    provisionar_odoo_sim.provisionar(cliente)
    info = odoo_cliente.resolver_coletor(cliente, provisionar_odoo_sim.COLETOR_CODE)
    assert info['site_code'] == provisionar_odoo_sim.SITE_CODE
