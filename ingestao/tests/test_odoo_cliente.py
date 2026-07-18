import pytest

from ingestao import odoo_cliente

ODOO_URL = 'http://localhost:8189'
ODOO_DB = 'sentinela'
ODOO_USUARIO = 'admin'
ODOO_SENHA = 'admin'


@pytest.fixture
def cliente():
    return odoo_cliente.conectar(ODOO_URL, ODOO_DB, ODOO_USUARIO, ODOO_SENHA)


def test_conectar_autentica_com_sucesso(cliente):
    assert cliente.uid


def test_conectar_falha_com_credenciais_erradas():
    with pytest.raises(RuntimeError):
        odoo_cliente.conectar(ODOO_URL, ODOO_DB, 'usuario_invalido_xyz', 'senha_invalida_xyz')


def test_resolver_coletor_existente(cliente):
    info = odoo_cliente.resolver_coletor(cliente, 'COL-01')
    assert info['site_code'] == 'CMEOX-01'
    assert info['id'] > 0
    assert info['hub_id'] > 0
    assert info['site_id'] > 0


def test_resolver_coletor_inexistente_levanta_erro(cliente):
    with pytest.raises(ValueError):
        odoo_cliente.resolver_coletor(cliente, 'COL-NAO-EXISTE-XYZ')
