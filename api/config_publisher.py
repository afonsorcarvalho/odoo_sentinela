"""Serializador Odoo -> config.yaml operacional consumido pelo Hub.

Lê a árvore Modbus de um hub (bus -> device -> profile -> sensores) e produz
o subconjunto OPERACIONAL do config (Global Constraints §7): barramentos,
dispositivos e canais com calibração/filtro. Não inclui identidade do hub
nem credenciais (hub_id, coletor_id, chaves, sftp, mqtt).
"""
from ingestao import odoo_cliente


def serializar_config_hub(cliente, hub_code):
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)

    hubs = ex('sensor_monitor.hub', 'search_read', [('hub_code', '=', hub_code)],
              fields=['id', 'config_version_desejada'])
    if not hubs:
        raise ValueError(f"hub '{hub_code}' não encontrado")
    hub = hubs[0]

    buses = ex('sensor_monitor.rs485.bus', 'search_read', [('hub_id', '=', hub['id'])],
               fields=['id', 'serial_port', 'baud_rate', 'parity', 'stop_bits'])
    barramentos = []
    for bus in buses:
        devices = ex('sensor_monitor.modbus.device', 'search_read',
                     [('rs485_bus_id', '=', bus['id'])],
                     fields=['id', 'slave_address', 'profile_id'])
        dispositivos = []
        for dev in devices:
            profile_id = dev['profile_id'][0]
            driver = ex('sensor_monitor.modbus.profile', 'read', [profile_id],
                        fields=['driver'])[0]['driver']
            regs = ex('sensor_monitor.modbus.profile.register', 'search',
                      [('profile_id', '=', profile_id)])
            sensores = ex('sensor_monitor.sensor', 'search_read',
                          [('modbus_register_id', 'in', regs)],
                          fields=['sensor_code', 'modbus_channel', 'ma_in_min', 'ma_in_max',
                                  'eng_out_min', 'eng_out_max', 'filtro_tipo', 'filtro_alpha',
                                  'unidade', 'protocolo_origem', 'area_id', 'measurement_type_id'])

            # area_id/measurement_type_id vêm como (id, display_name) via search_read;
            # o Hub espera os CÓDIGOS (area_code / measurement_type.code), não o nome
            # de exibição — resolve em lote.
            area_ids = {s['area_id'][0] for s in sensores if s.get('area_id')}
            areas_por_id = {}
            if area_ids:
                areas = ex('sensor_monitor.area', 'read', list(area_ids), fields=['area_code'])
                areas_por_id = {a['id']: a['area_code'] for a in areas}

            tipo_ids = {s['measurement_type_id'][0] for s in sensores if s.get('measurement_type_id')}
            tipos_por_id = {}
            if tipo_ids:
                tipos = ex('sensor_monitor.measurement.type', 'read', list(tipo_ids), fields=['code'])
                tipos_por_id = {t['id']: t['code'] for t in tipos}

            canais = []
            for s in sensores:
                canal = {
                    'ch': s['modbus_channel'],
                    'sensor_id': s['sensor_code'],
                    'area_id': areas_por_id.get(s['area_id'][0]) if s.get('area_id') else None,
                    'tipo_medida': tipos_por_id.get(s['measurement_type_id'][0]) if s.get('measurement_type_id') else None,
                    'unidade': s.get('unidade') or '',
                    # Fixo '4-20ma': rs485 é só o transporte físico do N4AIB16;
                    # o Hub espera o tipo de sinal do canal (spec §5.3/§7).
                    'protocolo_origem': '4-20ma',
                    'map': {'in': [s['ma_in_min'], s['ma_in_max']],
                            'out': [s['eng_out_min'], s['eng_out_max']]},
                }
                if s['filtro_tipo'] != 'none':
                    canal['filtro'] = {'tipo': s['filtro_tipo'], 'alpha': s['filtro_alpha']}
                canais.append(canal)

            dispositivos.append({'endereco': dev['slave_address'], 'driver': driver, 'canais': canais})

        barramentos.append({
            'porta': bus['serial_port'], 'baud': bus['baud_rate'],
            'paridade': bus['parity'], 'stop_bits': int(bus['stop_bits']),
            'dispositivos': dispositivos,
        })

    return {
        'version': hub['config_version_desejada'],
        'intervalo_leitura_s': 5,
        'barramentos': barramentos,
    }
