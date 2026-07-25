import pytest

from ingestao import odoo_cliente, provisionar_demo

from api.config_publisher import ConfigInvalida, serializar_config_hub
from api.odoo import get_cliente_servico

BUS_CODE = 'BUS-CFG-0'
SENSOR_CODE = 'SNR-EXP-TEMP-01'  # já criado por provisionar_demo, área AREA-EXPURGO

BUS_CODE_GEN = 'BUS-CFG-GEN-0'
SENSOR_CODE_GEN = 'SNR-EXP-PRES-01'  # já criado por provisionar_demo, área AREA-EXPURGO


def _prov_hub_modbus(cliente):
    """Reusa provisionar_demo (site/hub/coletor/área/sensor válidos) e completa
    a árvore Modbus (bus + profile + register + device) no hub demo, mapeando
    o sensor SNR-EXP-TEMP-01 ao canal 1 via write. Idempotente por códigos."""
    provisionar_demo.provisionar(cliente)
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)
    hub_code = provisionar_demo.HUB_CODE
    hub_id = ex('sensor_monitor.hub', 'search', [('hub_code', '=', hub_code)])[0]

    bus = ex('sensor_monitor.rs485.bus', 'search', [('bus_code', '=', BUS_CODE)]) or [
        ex('sensor_monitor.rs485.bus', 'create', {
            'hub_id': hub_id, 'name': 'Bus0 Cfg', 'bus_code': BUS_CODE,
            'serial_port': '/dev/ttyUSB0', 'baud_rate': 9600, 'parity': 'none',
            'stop_bits': '1', 'data_bits': 8})]
    bus_id = bus[0]

    prof = ex('sensor_monitor.modbus.profile', 'search', [('name', '=', 'N4AIB16 Cfg')]) or [
        ex('sensor_monitor.modbus.profile', 'create', {'name': 'N4AIB16 Cfg', 'driver': 'n4aib16'})]
    prof_id = prof[0]

    tipo_temp_id = ex('sensor_monitor.measurement.type', 'search', [('code', '=', 'temperatura')])[0]

    reg = ex('sensor_monitor.modbus.profile.register', 'search', [('name', '=', 'CH1 Cfg')]) or [
        ex('sensor_monitor.modbus.profile.register', 'create', {
            'profile_id': prof_id, 'name': 'CH1 Cfg',
            'measurement_type_id': tipo_temp_id,
            'function_code': '04_input', 'register_address': 1, 'register_count': 1,
            'data_type': 'int16'})]
    reg_id = reg[0]

    ex('sensor_monitor.modbus.device', 'search',
       [('rs485_bus_id', '=', bus_id), ('slave_address', '=', 1)]) or \
        ex('sensor_monitor.modbus.device', 'create', {
            'name': 'N4 Cfg', 'rs485_bus_id': bus_id, 'slave_address': 1, 'profile_id': prof_id})

    sensor_id = ex('sensor_monitor.sensor', 'search', [('sensor_code', '=', SENSOR_CODE)])[0]
    ex('sensor_monitor.sensor', 'write', [sensor_id], {
        'modbus_register_id': reg_id, 'modbus_channel': 1, 'ma_in_min': 4.0,
        'ma_in_max': 20.0, 'eng_out_min': -50.0, 'eng_out_max': 150.0,
        'filtro_tipo': 'ewma', 'filtro_alpha': 0.3, 'protocolo_origem': 'rs485',
        'usa_map': True})  # N4AIB16 é analógico 4-20mA: precisa do map in/out

    return hub_code


def _prov_hub_generico(cliente, data_type='int16', register_count=1, scale=0.1, offset=0.0):
    """Cria (idempotente por códigos) um device com perfil driver='generico' num
    bus próprio, um registrador (03_holding, addr 1) e o sensor SNR-EXP-PRES-01
    linkado, para testar a emissão de `registro` no canal.

    Reusa `_prov_hub_modbus` (em vez de chamar `provisionar_demo.provisionar`
    direto) para também deixar o bus/sensor N4 num estado válido — o hub demo
    é compartilhado entre todos os testes deste módulo, e qualquer teste pode
    ser o primeiro a rodar `serializar_config_hub` (que itera TODOS os
    barramentos do hub, N4 incluso)."""
    hub_code = _prov_hub_modbus(cliente)
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)
    hub_id = ex('sensor_monitor.hub', 'search', [('hub_code', '=', hub_code)])[0]

    bus = ex('sensor_monitor.rs485.bus', 'search', [('bus_code', '=', BUS_CODE_GEN)]) or [
        ex('sensor_monitor.rs485.bus', 'create', {
            'hub_id': hub_id, 'name': 'Bus Generico Cfg', 'bus_code': BUS_CODE_GEN,
            'serial_port': '/dev/ttyUSB1', 'baud_rate': 9600, 'parity': 'none',
            'stop_bits': '1', 'data_bits': 8})]
    bus_id = bus[0]

    prof = ex('sensor_monitor.modbus.profile', 'search', [('name', '=', 'Generico Cfg')]) or [
        ex('sensor_monitor.modbus.profile', 'create', {'name': 'Generico Cfg', 'driver': 'generico'})]
    prof_id = prof[0]

    tipo_pres_id = ex('sensor_monitor.measurement.type', 'search',
                      [('code', '=', 'pressao_diferencial')])[0]

    reg_vals = {
        'profile_id': prof_id, 'name': 'CH1 Generico Cfg',
        'measurement_type_id': tipo_pres_id,
        'function_code': '03_holding', 'register_address': 1, 'register_count': register_count,
        'data_type': data_type, 'scale': scale, 'offset': offset,
    }
    reg_existente = ex('sensor_monitor.modbus.profile.register', 'search',
                       [('name', '=', 'CH1 Generico Cfg')])
    if reg_existente:
        reg_id = reg_existente[0]
        ex('sensor_monitor.modbus.profile.register', 'write', [reg_id], reg_vals)
    else:
        reg_id = ex('sensor_monitor.modbus.profile.register', 'create', reg_vals)

    ex('sensor_monitor.modbus.device', 'search',
       [('rs485_bus_id', '=', bus_id), ('slave_address', '=', 2)]) or \
        ex('sensor_monitor.modbus.device', 'create', {
            'name': 'Generico Cfg', 'rs485_bus_id': bus_id, 'slave_address': 2, 'profile_id': prof_id})

    sensor_id = ex('sensor_monitor.sensor', 'search', [('sensor_code', '=', SENSOR_CODE_GEN)])[0]
    ex('sensor_monitor.sensor', 'write', [sensor_id], {
        'modbus_register_id': reg_id, 'modbus_channel': 1, 'protocolo_origem': 'rs485',
        'usa_map': False, 'filtro_tipo': 'none'})

    return hub_code


def test_serializar_driver_generico_emite_registro():
    cliente = get_cliente_servico()
    hub_code = _prov_hub_generico(cliente)

    cfg = serializar_config_hub(cliente, hub_code)

    bus = next(b for b in cfg['barramentos'] if b['porta'] == '/dev/ttyUSB1')
    disp = next(d for d in bus['dispositivos'] if d['endereco'] == 2)
    assert disp['driver'] == 'generico'
    canal = next(c for c in disp['canais'] if c['sensor_id'] == SENSOR_CODE_GEN)
    assert canal['registro'] == {
        'address': 1, 'function': 3, 'data_type': 'int16',
        'scale': 0.1, 'offset': 0.0, 'count': 1,
    }


def test_serializar_driver_generico_data_type_invalido_levanta():
    cliente = get_cliente_servico()
    hub_code = _prov_hub_generico(cliente, data_type='float32')

    try:
        with pytest.raises(ConfigInvalida):
            serializar_config_hub(cliente, hub_code)
    finally:
        # o bus/device genérico é compartilhado com o hub demo — devolve o
        # registrador a um estado válido para não quebrar os testes seguintes
        # que também iteram sobre todos os barramentos do hub.
        _prov_hub_generico(cliente)


def test_serializar_driver_generico_count_invalido_levanta():
    cliente = get_cliente_servico()
    hub_code = _prov_hub_generico(cliente, register_count=2)

    try:
        with pytest.raises(ConfigInvalida):
            serializar_config_hub(cliente, hub_code)
    finally:
        _prov_hub_generico(cliente)


def test_serializar_n4_nao_emite_registro():
    """Regressão: perfil N4AIB16 (register-based mas driver != generico) não
    deve ganhar `registro` no canal — só o driver genérico emite isso."""
    cliente = get_cliente_servico()
    hub_code = _prov_hub_modbus(cliente)

    cfg = serializar_config_hub(cliente, hub_code)

    bus = next(b for b in cfg['barramentos'] if b['porta'] == '/dev/ttyUSB0')
    disp = next(d for d in bus['dispositivos'] if d['endereco'] == 1)
    assert disp['driver'] == 'n4aib16'
    canal = next(c for c in disp['canais'] if c['sensor_id'] == SENSOR_CODE)
    assert 'registro' not in canal


def test_serializar_hub_produz_yaml_operacional():
    cliente = get_cliente_servico()
    hub_code = _prov_hub_modbus(cliente)

    cfg = serializar_config_hub(cliente, hub_code)

    assert cfg['version'] >= 1
    # sem identidade/creds do hub no config operacional
    for chave in ('hub_id', 'coletor_id', 'chaves', 'sftp', 'mqtt'):
        assert chave not in cfg

    bus = next(b for b in cfg['barramentos'] if b['porta'] == '/dev/ttyUSB0')
    assert bus['baud'] == 9600
    assert bus['paridade'] == 'N'
    assert bus['stop_bits'] == 1

    disp = next(d for d in bus['dispositivos'] if d['endereco'] == 1)
    assert disp['driver'] == 'n4aib16'

    canal = next(c for c in disp['canais'] if c['sensor_id'] == SENSOR_CODE)
    assert canal['ch'] == 1
    assert canal['area_id'] == 'AREA-EXPURGO'
    assert canal['tipo_medida'] == 'temperatura'
    assert canal['protocolo_origem'] == 'rs485'  # vem do campo, não hardcode
    assert canal['map'] == {'in': [4.0, 20.0], 'out': [-50.0, 150.0]}
    assert canal['filtro'] == {'tipo': 'ewma', 'alpha': 0.3}


def test_serializar_hub_inexistente_levanta_value_error():
    cliente = get_cliente_servico()
    try:
        serializar_config_hub(cliente, 'HUB-NAO-EXISTE-XYZ')
        assert False, 'esperado ValueError'
    except ValueError:
        pass


def test_canal_carrega_calibracao_vigente():
    from ingestao import odoo_cliente
    from api.config_publisher import serializar_config_hub
    from api.odoo import get_cliente_servico
    cliente = get_cliente_servico()
    hub_code = _prov_hub_modbus(cliente)
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)

    sensor_id = ex('sensor_monitor.sensor', 'search', [('sensor_code', '=', SENSOR_CODE)])[0]
    ex('sensor_monitor.sensor', 'write', [sensor_id], {'conversor_tipo': 'nenhum'})
    # cert vigente casando o conversor 'nenhum' — idempotente por (sensor_id, versao):
    # reaproveita o cert de execuções anteriores em vez de recriar (unique constraint).
    cert_existente = ex('sensor_monitor.calibracao', 'search',
                         [('sensor_id', '=', sensor_id), ('versao', '=', 7)])
    if not cert_existente:
        ex('sensor_monitor.calibracao', 'create', {
            'sensor_id': sensor_id, 'cert_numero': 'CERT-CFG', 'versao': 7,
            'cal_ganho': 0.965, 'cal_offset': 0.33,
            'validade_de': '2020-01-01', 'validade_ate': '2099-12-31',
            'conversor_tipo_snapshot': 'nenhum'})

    cfg = serializar_config_hub(cliente, hub_code)
    bus = next(b for b in cfg['barramentos'] if b['porta'] == '/dev/ttyUSB0')
    disp = next(d for d in bus['dispositivos'] if d['endereco'] == 1)
    canal = next(c for c in disp['canais'] if c['sensor_id'] == SENSOR_CODE)
    assert canal['calibracao'] == {'cert_ver': 7, 'ganho': 0.965, 'offset': 0.33}


def test_canal_sem_cert_emite_identidade():
    from ingestao import odoo_cliente
    from api.config_publisher import serializar_config_hub
    from api.odoo import get_cliente_servico
    cliente = get_cliente_servico()
    hub_code = _prov_hub_modbus(cliente)
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)
    # garante que o sensor não tem cert casando o conversor atual
    sensor_id = ex('sensor_monitor.sensor', 'search', [('sensor_code', '=', SENSOR_CODE)])[0]
    ex('sensor_monitor.sensor', 'write', [sensor_id], {'conversor_tipo': '485_0_30v'})

    cfg = serializar_config_hub(cliente, hub_code)
    bus = next(b for b in cfg['barramentos'] if b['porta'] == '/dev/ttyUSB0')
    disp = next(d for d in bus['dispositivos'] if d['endereco'] == 1)
    canal = next(c for c in disp['canais'] if c['sensor_id'] == SENSOR_CODE)
    assert canal['calibracao'] == {'cert_ver': 0, 'ganho': 1.0, 'offset': 0.0}


def test_config_traz_tenant_no_topo():
    from ingestao import odoo_cliente
    from api.config_publisher import serializar_config_hub
    from api.odoo import get_cliente_servico
    cliente = get_cliente_servico()
    hub_code = _prov_hub_modbus(cliente)
    cfg = serializar_config_hub(cliente, hub_code)
    assert cfg['site_id']  # site_code do site do hub
    assert cfg['cliente_id']  # partner.ref ou CLI-<id>


def test_usa_map_true_emite_map():
    cliente = get_cliente_servico()
    _prov_hub_modbus(cliente)
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)
    sid = ex('sensor_monitor.sensor', 'search', [('sensor_code', '=', SENSOR_CODE)])[0]
    ex('sensor_monitor.sensor', 'write', [sid], {'usa_map': True})
    cfg = serializar_config_hub(cliente, provisionar_demo.HUB_CODE)
    canal = cfg['barramentos'][0]['dispositivos'][0]['canais'][0]
    assert 'map' in canal
    assert canal['protocolo_origem'] == 'rs485'   # vem do campo, não hardcode


def test_usa_map_false_omite_map():
    cliente = get_cliente_servico()
    _prov_hub_modbus(cliente)
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)
    sid = ex('sensor_monitor.sensor', 'search', [('sensor_code', '=', SENSOR_CODE)])[0]
    ex('sensor_monitor.sensor', 'write', [sid], {'usa_map': False,
        'eng_out_min': 0.0, 'eng_out_max': 0.0})   # map degenerado, mas nativo → OK
    cfg = serializar_config_hub(cliente, provisionar_demo.HUB_CODE)
    canal = cfg['barramentos'][0]['dispositivos'][0]['canais'][0]
    assert 'map' not in canal


def test_usa_map_true_map_degenerado_levanta():
    from api.config_publisher import ConfigInvalida
    cliente = get_cliente_servico()
    _prov_hub_modbus(cliente)
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)
    sid = ex('sensor_monitor.sensor', 'search', [('sensor_code', '=', SENSOR_CODE)])[0]
    ex('sensor_monitor.sensor', 'write', [sid], {'usa_map': True,
        'eng_out_min': 0.0, 'eng_out_max': 0.0})
    with pytest.raises(ConfigInvalida):
        serializar_config_hub(cliente, provisionar_demo.HUB_CODE)


def test_exigir_driver_conhecido_rejeita_desconhecido():
    from api.config_publisher import _exigir_driver_conhecido, ConfigInvalida
    with pytest.raises(ConfigInvalida):
        _exigir_driver_conhecido('driver_inexistente', 2, 'HUB-X')


def test_exigir_driver_conhecido_aceita_conhecidos():
    from api.config_publisher import _exigir_driver_conhecido
    _exigir_driver_conhecido('n4aib16', 1, 'HUB-X')      # não levanta
    _exigir_driver_conhecido('rs_ws_n01_2d', 2, 'HUB-X')  # não levanta
