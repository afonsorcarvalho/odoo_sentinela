from api import config_publisher


def _fake_executar(respostas):
    """respostas: função (model, metodo, *args, **kw) -> valor, roteando por (model, metodo)."""
    def ex(cliente, model, metodo, *args, **kw):
        return respostas(model, metodo, args, kw)
    return ex


def test_canal_recebe_limite_quando_ha_threshold(monkeypatch):
    def respostas(model, metodo, args, kw):
        if model == 'sensor_monitor.hub' and metodo == 'search_read':
            return [{'id': 1, 'config_version_desejada': 7}]
        if model == 'sensor_monitor.rs485.bus' and metodo == 'search_read':
            return [{'id': 10, 'serial_port': '/dev/ttyUSB0', 'baud_rate': 9600,
                     'parity': 'none', 'stop_bits': 1}]
        if model == 'sensor_monitor.modbus.device' and metodo == 'search_read':
            return [{'id': 20, 'slave_address': 1, 'profile_id': (30, 'P'),
                     'reconexao_n': 3, 'reconexao_m': 5, 'reconexao_k': 10}]
        if model == 'sensor_monitor.modbus.profile' and metodo == 'read':
            return [{'driver': 'n4aib16'}]
        if model == 'sensor_monitor.modbus.profile.register' and metodo == 'search':
            return [40]
        if model == 'sensor_monitor.sensor' and metodo == 'search_read':
            return [{'sensor_code': 'SNR-T-01', 'modbus_channel': 1, 'ma_in_min': 4,
                     'ma_in_max': 20, 'eng_out_min': 0, 'eng_out_max': 100,
                     'filtro_tipo': 'none', 'filtro_alpha': 0.0, 'unidade': 'C',
                     'protocolo_origem': 'rs485', 'area_id': (50, 'Area'),
                     'measurement_type_id': (60, 'Temp'), 'calibracao_vigente_id': False,
                     'usa_map': False, 'modbus_register_id': (40, 'R'),
                     'usa_faixa': False, 'faixa_min': 0, 'faixa_max': 0, 'id': 70}]
        if model == 'sensor_monitor.alarm.threshold' and metodo == 'search_read':
            return [{'sensor_id': (70, 'SNR-T-01'), 'limite_min': 18.0, 'limite_max': 25.0}]
        if model == 'sensor_monitor.area' and metodo == 'read':
            return [{'id': 50, 'area_code': 'AREA-T'}]
        if model == 'sensor_monitor.measurement.type' and metodo == 'read':
            return [{'id': 60, 'code': 'temperatura'}]
        if model == 'sensor_monitor.hub' and metodo == 'read':
            return [{'site_id': (80, 'Site')}]
        if model == 'sensor_monitor.site' and metodo == 'read':
            return [{'site_code': 'SITE-T', 'partner_id': (90, 'P')}]
        if model == 'res.partner' and metodo == 'read':
            return [{'ref': 'CLI-T'}]
        raise AssertionError(f"chamada inesperada: {model}.{metodo}")

    monkeypatch.setattr(config_publisher.odoo_cliente, 'executar', _fake_executar(respostas))
    cfg = config_publisher.serializar_config_hub(cliente=None, hub_code='HUB-T')
    canal = cfg['barramentos'][0]['dispositivos'][0]['canais'][0]
    assert canal['limite_min'] == 18.0
    assert canal['limite_max'] == 25.0


def test_canal_sem_threshold_nao_tem_limite(monkeypatch):
    def respostas(model, metodo, args, kw):
        if model == 'sensor_monitor.hub' and metodo == 'search_read':
            return [{'id': 1, 'config_version_desejada': 7}]
        if model == 'sensor_monitor.rs485.bus' and metodo == 'search_read':
            return [{'id': 10, 'serial_port': '/dev/ttyUSB0', 'baud_rate': 9600,
                     'parity': 'none', 'stop_bits': 1}]
        if model == 'sensor_monitor.modbus.device' and metodo == 'search_read':
            return [{'id': 20, 'slave_address': 1, 'profile_id': (30, 'P'),
                     'reconexao_n': 3, 'reconexao_m': 5, 'reconexao_k': 10}]
        if model == 'sensor_monitor.modbus.profile' and metodo == 'read':
            return [{'driver': 'n4aib16'}]
        if model == 'sensor_monitor.modbus.profile.register' and metodo == 'search':
            return [40]
        if model == 'sensor_monitor.sensor' and metodo == 'search_read':
            return [{'sensor_code': 'SNR-T-01', 'modbus_channel': 1, 'ma_in_min': 4,
                     'ma_in_max': 20, 'eng_out_min': 0, 'eng_out_max': 100,
                     'filtro_tipo': 'none', 'filtro_alpha': 0.0, 'unidade': 'C',
                     'protocolo_origem': 'rs485', 'area_id': (50, 'Area'),
                     'measurement_type_id': (60, 'Temp'), 'calibracao_vigente_id': False,
                     'usa_map': False, 'modbus_register_id': (40, 'R'),
                     'usa_faixa': False, 'faixa_min': 0, 'faixa_max': 0, 'id': 70}]
        if model == 'sensor_monitor.alarm.threshold' and metodo == 'search_read':
            return []
        if model == 'sensor_monitor.area' and metodo == 'read':
            return [{'id': 50, 'area_code': 'AREA-T'}]
        if model == 'sensor_monitor.measurement.type' and metodo == 'read':
            return [{'id': 60, 'code': 'temperatura'}]
        if model == 'sensor_monitor.hub' and metodo == 'read':
            return [{'site_id': (80, 'Site')}]
        if model == 'sensor_monitor.site' and metodo == 'read':
            return [{'site_code': 'SITE-T', 'partner_id': (90, 'P')}]
        if model == 'res.partner' and metodo == 'read':
            return [{'ref': 'CLI-T'}]
        raise AssertionError(f"chamada inesperada: {model}.{metodo}")

    monkeypatch.setattr(config_publisher.odoo_cliente, 'executar', _fake_executar(respostas))
    cfg = config_publisher.serializar_config_hub(cliente=None, hub_code='HUB-T')
    canal = cfg['barramentos'][0]['dispositivos'][0]['canais'][0]
    assert 'limite_min' not in canal and 'limite_max' not in canal
