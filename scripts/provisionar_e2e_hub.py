"""Provisiona o cenário E2E do Plano B (Fase 5) no Odoo: hub HUB-E2E-01 + árvore
Modbus (bus RS-485 /dev/ttyUSB0 → device N4AIB16 addr 1 → perfil/registrador) +
sensor SNR-E2E-CH1 mapeado ao canal físico 1 do N4AIB16 (18,4mA na bancada).

Idempotente (search-or-create). Reusa a base demo (site/área/coletor/measurement_type)
via ingestao.provisionar_demo. Rodar da raiz do repo com o .venv.
"""
from api.odoo import get_cliente_servico
from ingestao import odoo_cliente, provisionar_demo

HUB_CODE = 'HUB-E2E-01'
SENSOR_CODE = 'SNR-E2E-CH1'


def _soc(ex, model, dominio, vals):
    """search-or-create: devolve o id."""
    achados = ex(model, 'search', dominio)
    return achados[0] if achados else ex(model, 'create', vals)


def main():
    cliente = get_cliente_servico()
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)

    # base demo (site SITE-DEMO-01, áreas, coletor COL-DEMO-01, measurement_types)
    provisionar_demo.provisionar(cliente)
    site_id = ex('sensor_monitor.site', 'search', [('site_code', '=', provisionar_demo.SITE_CODE)])[0]
    coletor_id = ex('sensor_monitor.coletor', 'search', [('coletor_code', '=', provisionar_demo.COLETOR_CODE)])[0]
    area_id = ex('sensor_monitor.area', 'search', [('area_code', '=', 'AREA-EXPURGO')])[0]
    mt_id = ex('sensor_monitor.measurement.type', 'search', [('code', '=', 'temperatura')])[0]

    hub_id = _soc(ex, 'sensor_monitor.hub', [('hub_code', '=', HUB_CODE)],
                  {'name': 'Hub E2E', 'site_id': site_id, 'hub_code': HUB_CODE})
    bus_id = _soc(ex, 'sensor_monitor.rs485.bus', [('bus_code', '=', 'BUS-E2E-0')],
                  {'hub_id': hub_id, 'name': 'Bus0 E2E', 'bus_code': 'BUS-E2E-0',
                   'serial_port': '/dev/ttyUSB0', 'baud_rate': 9600, 'parity': 'none',
                   'stop_bits': '1', 'data_bits': 8})
    prof_id = _soc(ex, 'sensor_monitor.modbus.profile', [('name', '=', 'N4AIB16 E2E')],
                   {'name': 'N4AIB16 E2E', 'driver': 'n4aib16'})
    reg_id = _soc(ex, 'sensor_monitor.modbus.profile.register', [('name', '=', 'CH1 E2E')],
                  {'profile_id': prof_id, 'name': 'CH1 E2E', 'measurement_type_id': mt_id,
                   'function_code': '04_input', 'register_address': 0, 'register_count': 1,
                   'data_type': 'int16'})
    _soc(ex, 'sensor_monitor.modbus.device',
         [('rs485_bus_id', '=', bus_id), ('slave_address', '=', 1)],
         {'name': 'N4AIB16 addr1', 'rs485_bus_id': bus_id, 'slave_address': 1, 'profile_id': prof_id})

    vals_sensor = {
        'name': 'Temperatura CH1 (E2E)', 'sensor_code': SENSOR_CODE,
        'coletor_id': coletor_id, 'area_id': area_id, 'measurement_type_id': mt_id,
        'protocolo_origem': 'rs485', 'modbus_register_id': reg_id, 'modbus_channel': 1,
        'ma_in_min': 4.0, 'ma_in_max': 20.0, 'eng_out_min': -50.0, 'eng_out_max': 150.0,
        'filtro_tipo': 'none',
    }
    sensores = ex('sensor_monitor.sensor', 'search', [('sensor_code', '=', SENSOR_CODE)])
    if sensores:
        ex('sensor_monitor.sensor', 'write', [sensores[0]], vals_sensor)
        sensor_id = sensores[0]
    else:
        sensor_id = ex('sensor_monitor.sensor', 'create', vals_sensor)

    print(f'OK provisionado: hub={hub_id} ({HUB_CODE}) bus={bus_id} device_addr=1 '
          f'reg={reg_id} sensor={sensor_id} ({SENSOR_CODE} ch1)')


if __name__ == '__main__':
    main()
