"""Provisiona no Odoo o hub HUB-OXIMED-01 (Pi com N4AIB16 direto na serial RS-485):
cliente OXIMED -> SITE-001 -> hub -> coletor lógico -> barramento -> N4AIB16 addr 1
-> sensor de ETO (óxido de etileno) no CH1, 4-20 mA -> 0-100 ppm.

Idempotente (search-or-create; o sensor é atualizado). Rodar da raiz com o .venv.
"""
from api.odoo import get_cliente_servico
from ingestao import odoo_cliente

CLIENTE_REF = 'OXIMED'
SITE_CODE = 'SITE-001'
HUB_CODE = 'HUB-OXIMED-01'
COLETOR_CODE = 'COL-OXIMED-BUS0'
BUS_CODE = 'BUS-OXIMED-0'
AREA_CODE = 'AREA-OXIMED-ETO'
SENSOR_CODE = 'SNR-OXIMED-ETO-01'
PORTA = '/dev/ttyUSB0'
CANAL = 1


def _soc(ex, model, dominio, vals):
    achados = ex(model, 'search', dominio)
    return achados[0] if achados else ex(model, 'create', vals)


def main():
    cliente = get_cliente_servico()
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)

    partner_id = ex('res.partner', 'search', [('ref', '=', CLIENTE_REF)])[0]
    site_id = _soc(ex, 'sensor_monitor.site', [('site_code', '=', SITE_CODE)],
                   {'name': 'OXIMED — Site 001', 'partner_id': partner_id,
                    'site_code': SITE_CODE, 'vertical': 'industrial_generico'})
    hub_id = _soc(ex, 'sensor_monitor.hub', [('hub_code', '=', HUB_CODE)],
                  {'name': 'Hub OXIMED 01', 'site_id': site_id, 'hub_code': HUB_CODE})
    coletor_id = _soc(ex, 'sensor_monitor.coletor', [('coletor_code', '=', COLETOR_CODE),
                                                     ('hub_id', '=', hub_id)],
                      {'name': 'Coletor RS-485 OXIMED', 'hub_id': hub_id,
                       'coletor_code': COLETOR_CODE, 'tipo': 'hub_rs485_embutido'})
    cat_id = ex('sensor_monitor.area.category', 'search', [('code', '=', 'PREPARO_ESTERILIZACAO')])[0]
    area_id = _soc(ex, 'sensor_monitor.area', [('area_code', '=', AREA_CODE)],
                   {'name': 'Esterilização ETO', 'site_id': site_id,
                    'area_category_id': cat_id, 'area_code': AREA_CODE})
    mt_id = _soc(ex, 'sensor_monitor.measurement.type', [('code', '=', 'eto')],
                 {'name': 'Óxido de Etileno (ETO)', 'code': 'eto', 'unidade_padrao': 'ppm'})

    bus_id = _soc(ex, 'sensor_monitor.rs485.bus', [('bus_code', '=', BUS_CODE)],
                  {'hub_id': hub_id, 'name': 'Bus0 OXIMED', 'bus_code': BUS_CODE,
                   'serial_port': PORTA, 'baud_rate': 9600, 'parity': 'none',
                   'stop_bits': '1', 'data_bits': 8})
    prof_id = _soc(ex, 'sensor_monitor.modbus.profile', [('name', '=', 'N4AIB16 OXIMED')],
                   {'name': 'N4AIB16 OXIMED', 'driver': 'n4aib16'})
    reg_id = _soc(ex, 'sensor_monitor.modbus.profile.register', [('name', '=', 'CH1 OXIMED')],
                  {'profile_id': prof_id, 'name': 'CH1 OXIMED', 'measurement_type_id': mt_id,
                   'function_code': '04_input', 'register_address': 0, 'register_count': 1,
                   'data_type': 'int16'})
    _soc(ex, 'sensor_monitor.modbus.device',
         [('rs485_bus_id', '=', bus_id), ('slave_address', '=', 1)],
         {'name': 'N4AIB16 addr1 OXIMED', 'rs485_bus_id': bus_id, 'slave_address': 1,
          'profile_id': prof_id})

    vals = {
        'name': 'ETO CH1', 'sensor_code': SENSOR_CODE, 'coletor_id': coletor_id,
        'area_id': area_id, 'measurement_type_id': mt_id, 'protocolo_origem': 'rs485',
        'modbus_register_id': reg_id, 'modbus_channel': CANAL,
        'ma_in_min': 4.0, 'ma_in_max': 20.0, 'eng_out_min': 0.0, 'eng_out_max': 100.0,
        'filtro_tipo': 'none', 'usa_map': True, 'unidade': 'ppm',
    }
    existentes = ex('sensor_monitor.sensor', 'search', [('sensor_code', '=', SENSOR_CODE)])
    if existentes:
        ex('sensor_monitor.sensor', 'write', existentes, vals)
        sensor_id = existentes[0]
    else:
        sensor_id = ex('sensor_monitor.sensor', 'create', vals)
    print(f'OK: site={site_id} hub={hub_id} coletor={coletor_id} bus={bus_id} '
          f'area={area_id} sensor={sensor_id} ({SENSOR_CODE} ch{CANAL}, 4-20mA -> 0-100 ppm)')


if __name__ == '__main__':
    main()
