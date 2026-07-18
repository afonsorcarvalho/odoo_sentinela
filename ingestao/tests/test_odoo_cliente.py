import pytest

from ingestao import odoo_cliente, provisionar_odoo_sim

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


def test_escrever_ledger_cria_e_atualiza(cliente):
    provisionar_odoo_sim.provisionar(cliente)
    info = odoo_cliente.resolver_coletor(cliente, provisionar_odoo_sim.COLETOR_CODE)
    data_ref = '2020-01-01'  # data de teste, isolada de qualquer arquivo real gerado

    id1 = odoo_cliente.escrever_ledger(
        cliente, info['id'], 'leituras', data_ref, 'valido', None, 2880, 'hash-teste-1', 'assinatura-teste-1',
    )
    try:
        id2 = odoo_cliente.escrever_ledger(
            cliente, info['id'], 'leituras', data_ref, 'valido', None, 2880, 'hash-teste-2', 'assinatura-teste-2',
        )
        assert id1 == id2

        registros = odoo_cliente.executar(
            cliente, 'sensor_monitor.file.ledger', 'read', [id1], fields=['hash_final', 'status_validacao'],
        )
        assert registros[0]['hash_final'] == 'hash-teste-2'
        assert registros[0]['status_validacao'] == 'valido'
    finally:
        odoo_cliente.executar(cliente, 'sensor_monitor.file.ledger', 'unlink', [id1])
