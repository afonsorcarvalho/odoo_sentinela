"""Serializador Odoo -> config.yaml operacional consumido pelo Hub.

Lê a árvore Modbus de um hub (bus -> device -> profile -> sensores) e produz
o subconjunto OPERACIONAL do config (Global Constraints §7): barramentos,
dispositivos e canais com calibração/filtro. Não inclui identidade do hub
nem credenciais (hub_id, coletor_id, chaves, sftp, mqtt).
"""
import os

import paramiko

from ingestao import odoo_cliente

_SFTP_BASE = '/config'

# Hub espera 'N'/'E'/'O'; o Selection do Odoo é 'none'/'even'/'odd'.
_PARIDADE_MAP = {'none': 'N', 'even': 'E', 'odd': 'O'}


def _sftp_conectar():
    t = paramiko.Transport((os.environ['SFTP_HOST'], int(os.environ.get('SFTP_PORT', '2022'))))
    t.connect(username=os.environ['SFTP_USER'],
              pkey=paramiko.Ed25519Key.from_private_key_file(os.environ['SFTP_KEY_PATH']))
    return t, paramiko.SFTPClient.from_transport(t)


def escrever_config_sftp(hub_code, version, conteudo_yaml):
    """Grava /config/<hub_code>/config-v<version>.yaml no SFTPGo via SFTP.

    Cria o subdiretório do hub se ainda não existir. Devolve o caminho remoto.
    """
    t, sftp = _sftp_conectar()
    try:
        dir_hub = f'{_SFTP_BASE}/{hub_code}'
        try:
            sftp.stat(dir_hub)
        except FileNotFoundError:
            sftp.mkdir(dir_hub)
        remoto = f'{dir_hub}/config-v{version}.yaml'
        with sftp.open(remoto, 'w') as f:
            f.write(conteudo_yaml)
        return remoto
    finally:
        t.close()


def serializar_config_hub(cliente, hub_code, version=None):
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
                                  'unidade', 'protocolo_origem', 'area_id', 'measurement_type_id',
                                  'calibracao_vigente_id'])

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

            cert_ids = {s['calibracao_vigente_id'][0] for s in sensores if s.get('calibracao_vigente_id')}
            certs_por_id = {}
            if cert_ids:
                certs = ex('sensor_monitor.calibracao', 'read', list(cert_ids),
                           fields=['versao', 'cal_ganho', 'cal_offset'])
                certs_por_id = {c['id']: c for c in certs}

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
                cert = certs_por_id.get(s['calibracao_vigente_id'][0]) if s.get('calibracao_vigente_id') else None
                canal['calibracao'] = {
                    'cert_ver': cert['versao'] if cert else 0,
                    'ganho': cert['cal_ganho'] if cert else 1.0,
                    'offset': cert['cal_offset'] if cert else 0.0,
                }
                canais.append(canal)

            dispositivos.append({'endereco': dev['slave_address'], 'driver': driver, 'canais': canais})

        barramentos.append({
            'porta': bus['serial_port'], 'baud': bus['baud_rate'],
            'paridade': _PARIDADE_MAP.get(bus['parity'], bus['parity']),
            'stop_bits': int(bus['stop_bits']),
            'dispositivos': dispositivos,
        })

    return {
        'version': version if version is not None else hub['config_version_desejada'],
        'intervalo_leitura_s': 5,
        'barramentos': barramentos,
    }
