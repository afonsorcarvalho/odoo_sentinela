from datetime import datetime, timedelta, timezone

import pytest

from api.odoo import get_cliente_servico
from api.relatorio_odoo import alarmes_periodo, alteracoes_limite, nome_emissor
from api.tests.tenant_fixtures import criar_tenant, remover_tenant
from ingestao import odoo_cliente

_FMT = '%Y-%m-%d %H:%M:%S'


@pytest.fixture
def tenant():
    dados = criar_tenant('RELODOO')
    yield dados
    cliente = get_cliente_servico()
    ids = odoo_cliente.executar(
        cliente, 'sensor_monitor.alarm.event', 'search', [('sensor_id', '=', dados['sensor_id'])],
    )
    if ids:
        odoo_cliente.executar(cliente, 'sensor_monitor.alarm.event', 'unlink', ids)
    ths = odoo_cliente.executar(
        cliente, 'sensor_monitor.alarm.threshold', 'search', [('sensor_id', '=', dados['sensor_id'])],
    )
    if ths:
        odoo_cliente.executar(cliente, 'sensor_monitor.alarm.threshold', 'unlink', ths)
    remover_tenant(dados)


def _evento(cliente, dados, deteccao, resolucao=None, manual=None):
    sensor = odoo_cliente.executar(
        cliente, 'sensor_monitor.sensor', 'read', [dados['sensor_id']], fields=['area_id'],
    )[0]
    valores = {
        'sensor_id': dados['sensor_id'],
        'area_id': sensor['area_id'][0],
        'timestamp_deteccao': deteccao.strftime(_FMT),
        'valor_lido': 99.9,
        'tipo_violacao': 'acima_limite',
        'limite_configurado_snapshot': 30.0,
        'status': 'resolvido' if (resolucao or manual) else 'aberto',
    }
    if resolucao:
        valores['timestamp_resolucao_sensor'] = resolucao.strftime(_FMT)
    if manual:
        valores['data_resolucao'] = manual.strftime(_FMT)
    return odoo_cliente.executar(cliente, 'sensor_monitor.alarm.event', 'create', valores)


def test_alarme_aberto_antes_do_periodo_aparece(tenant):
    cliente = get_cliente_servico()
    inicio = datetime(2026, 3, 10, 3, 0, tzinfo=timezone.utc)
    fim = inicio + timedelta(days=1)
    evento_id = _evento(cliente, tenant, inicio - timedelta(days=5))
    resultado = alarmes_periodo(cliente, tenant['sensor_code'], inicio, fim)
    assert [e['id'] for e in resultado] == [evento_id]
    assert resultado[0]['sensor_code'] == tenant['sensor_code']


def test_alarme_resolvido_antes_do_periodo_nao_aparece(tenant):
    cliente = get_cliente_servico()
    inicio = datetime(2026, 3, 10, 3, 0, tzinfo=timezone.utc)
    fim = inicio + timedelta(days=1)
    _evento(cliente, tenant, inicio - timedelta(days=5), inicio - timedelta(days=4))
    assert alarmes_periodo(cliente, tenant['sensor_code'], inicio, fim) == []


def test_alarme_apos_o_periodo_nao_aparece_e_resolvido_dentro_aparece(tenant):
    cliente = get_cliente_servico()
    inicio = datetime(2026, 3, 10, 3, 0, tzinfo=timezone.utc)
    fim = inicio + timedelta(days=1)
    _evento(cliente, tenant, fim + timedelta(hours=1))
    dentro = _evento(cliente, tenant, inicio - timedelta(days=2), inicio + timedelta(hours=1))
    assert [e['id'] for e in alarmes_periodo(cliente, tenant['sensor_code'], inicio, fim)] == [dentro]


def test_alteracoes_limite_retorna_mudanca(tenant):
    cliente = get_cliente_servico()
    th_id = odoo_cliente.executar(
        cliente, 'sensor_monitor.alarm.threshold', 'create',
        {'sensor_id': tenant['sensor_id'], 'limite_min': 18.0, 'limite_max': 30.0,
         'is_valor_padrao_regulatorio': True},
    )
    antes = datetime.now(timezone.utc) - timedelta(minutes=5)
    odoo_cliente.executar(cliente, 'sensor_monitor.alarm.threshold', 'write', [th_id], {'limite_max': 35.0})
    resultado = alteracoes_limite(cliente, tenant['sensor_code'], antes)
    item = next(a for a in resultado if a['campo'] == 'limite_max')
    assert item['de'] == 30.0
    assert item['para'] == 35.0
    assert item['quando'].tzinfo is not None
    assert item['quando'] >= antes


def test_alteracoes_limite_sem_threshold_retorna_vazio(tenant):
    cliente = get_cliente_servico()
    assert alteracoes_limite(cliente, tenant['sensor_code'], datetime(2020, 1, 1, tzinfo=timezone.utc)) == []


def test_nome_emissor_contem_login():
    cliente = get_cliente_servico()
    texto = nome_emissor(cliente)
    assert '(admin)' in texto


def test_resolvido_manualmente_antes_do_periodo_nao_aparece(tenant):
    cliente = get_cliente_servico()
    inicio = datetime(2026, 3, 10, 3, 0, tzinfo=timezone.utc)
    fim = inicio + timedelta(days=1)
    _evento(cliente, tenant, inicio - timedelta(days=5), manual=inicio - timedelta(days=4))
    assert alarmes_periodo(cliente, tenant['sensor_code'], inicio, fim) == []


def test_resolvido_manualmente_dentro_do_periodo_aparece(tenant):
    cliente = get_cliente_servico()
    inicio = datetime(2026, 3, 10, 3, 0, tzinfo=timezone.utc)
    fim = inicio + timedelta(days=1)
    dentro = _evento(cliente, tenant, inicio - timedelta(days=5), manual=inicio + timedelta(hours=2))
    assert [e['id'] for e in alarmes_periodo(cliente, tenant['sensor_code'], inicio, fim)] == [dentro]
