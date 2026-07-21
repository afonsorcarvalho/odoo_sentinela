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
    provisionar_odoo_sim.provisionar(cliente)
    info = odoo_cliente.resolver_coletor(cliente, provisionar_odoo_sim.COLETOR_CODE)
    assert info['site_code'] == provisionar_odoo_sim.SITE_CODE
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


def test_resolver_sensor_existente(cliente):
    provisionar_odoo_sim.provisionar(cliente)
    info = odoo_cliente.resolver_sensor(cliente, 'SNR-SIM-TEMP-01')
    assert info['id'] > 0
    assert info['area_id'] > 0


def test_resolver_sensor_inexistente_levanta_erro(cliente):
    with pytest.raises(ValueError):
        odoo_cliente.resolver_sensor(cliente, 'SNR-NAO-EXISTE-XYZ')


def test_processar_entrada_e_saida_alarme(cliente):
    provisionar_odoo_sim.provisionar(cliente)
    info_sensor = odoo_cliente.resolver_sensor(cliente, 'SNR-SIM-PRES-01')
    info_coletor = odoo_cliente.resolver_coletor(cliente, provisionar_odoo_sim.COLETOR_CODE)

    evento_entrada = {
        'timestamp': '2020-02-02T02:00:00-03:00', 'valor': 1.0,
        'tipo_violacao': 'acima_limite', 'limite_min_vigente': None, 'limite_max_vigente': -2.5,
    }
    evento_id = odoo_cliente.processar_entrada_alarme(
        cliente, evento_entrada, info_sensor['id'], info_sensor['area_id'], info_coletor['id'], 'hash-teste',
    )
    try:
        registros = odoo_cliente.executar(
            cliente, 'sensor_monitor.alarm.event', 'read', [evento_id],
            fields=['status', 'timestamp_resolucao_sensor', 'limite_configurado_snapshot'],
        )
        assert registros[0]['status'] == 'aberto'
        assert registros[0]['timestamp_resolucao_sensor'] is False
        assert registros[0]['limite_configurado_snapshot'] == -2.5

        evento_saida = {'timestamp': '2020-02-02T02:07:00-03:00'}
        resolvido_id = odoo_cliente.processar_saida_alarme(cliente, evento_saida, info_sensor['id'])
        assert resolvido_id == evento_id

        registros = odoo_cliente.executar(
            cliente, 'sensor_monitor.alarm.event', 'read', [evento_id], fields=['timestamp_resolucao_sensor'],
        )
        assert registros[0]['timestamp_resolucao_sensor'] is not False
    finally:
        odoo_cliente.executar(cliente, 'sensor_monitor.alarm.event', 'unlink', [evento_id])


def test_processar_saida_alarme_sem_entrada_aberta_retorna_none(cliente):
    provisionar_odoo_sim.provisionar(cliente)
    info_sensor = odoo_cliente.resolver_sensor(cliente, 'SNR-SIM-TEMP-01')

    # Garante a pre-condicao do teste (nenhuma entrada aberta pra esse sensor)
    # em vez de assumir estado ambiente do Odoo compartilhado — sem isso, um
    # alarm.event orfao de outra execucao faz este teste falhar de forma
    # dificil de diagnosticar (o proprio ato de testar resolve o orfao).
    abertos_previos = odoo_cliente.executar(
        cliente, 'sensor_monitor.alarm.event', 'search',
        [('sensor_id', '=', info_sensor['id']), ('timestamp_resolucao_sensor', '=', False)],
    )
    if abertos_previos:
        odoo_cliente.executar(cliente, 'sensor_monitor.alarm.event', 'unlink', abertos_previos)

    evento_saida = {'timestamp': '2020-03-03T03:00:00-03:00'}
    resultado = odoo_cliente.processar_saida_alarme(cliente, evento_saida, info_sensor['id'])
    assert resultado is None
