import argparse

from . import odoo_cliente

PARTNER_NAME = 'Cliente Simulado'
SITE_CODE = 'SITE-SIM-0001'
HUB_CODE = 'HUB-SIM-0001'
AREA_CODE = 'AREA-SIM-EXPURGO'
COLETOR_CODE = 'COL-SIM-0001'
SENSORES = [
    {'sensor_code': 'SNR-SIM-TEMP-01', 'name': 'Temperatura Simulada', 'measurement_type_code': 'temperatura'},
    {'sensor_code': 'SNR-SIM-PRES-01', 'name': 'Pressão Simulada', 'measurement_type_code': 'pressao_diferencial'},
]


def _buscar_ou_criar(cliente, model, domain, valores):
    encontrados = odoo_cliente.executar(cliente, model, 'search', domain)
    if encontrados:
        return encontrados[0]
    return odoo_cliente.executar(cliente, model, 'create', valores)


def _buscar_id(cliente, model, domain):
    encontrados = odoo_cliente.executar(cliente, model, 'search', domain)
    if not encontrados:
        raise ValueError(f"registro não encontrado em {model} para {domain}")
    return encontrados[0]


def provisionar(cliente):
    partner_id = _buscar_ou_criar(
        cliente, 'res.partner', [('name', '=', PARTNER_NAME)], {'name': PARTNER_NAME},
    )
    site_id = _buscar_ou_criar(
        cliente, 'sensor_monitor.site', [('site_code', '=', SITE_CODE)],
        {'name': 'Site Simulado', 'partner_id': partner_id, 'site_code': SITE_CODE, 'vertical': 'cme_hospitalar'},
    )
    hub_id = _buscar_ou_criar(
        cliente, 'sensor_monitor.hub', [('hub_code', '=', HUB_CODE)],
        {'name': 'Hub Simulado', 'site_id': site_id, 'hub_code': HUB_CODE},
    )
    area_category_id = _buscar_id(cliente, 'sensor_monitor.area.category', [('code', '=', 'EXPURGO')])
    area_id = _buscar_ou_criar(
        cliente, 'sensor_monitor.area', [('area_code', '=', AREA_CODE)],
        {
            'name': 'Expurgo Simulado', 'site_id': site_id,
            'area_category_id': area_category_id, 'area_code': AREA_CODE,
        },
    )
    coletor_id = _buscar_ou_criar(
        cliente, 'sensor_monitor.coletor', [('coletor_code', '=', COLETOR_CODE)],
        {'name': 'Coletor Simulado', 'hub_id': hub_id, 'coletor_code': COLETOR_CODE, 'tipo': 'esp32_wifi'},
    )
    for sensor in SENSORES:
        measurement_type_id = _buscar_id(
            cliente, 'sensor_monitor.measurement.type', [('code', '=', sensor['measurement_type_code'])],
        )
        _buscar_ou_criar(
            cliente, 'sensor_monitor.sensor', [('sensor_code', '=', sensor['sensor_code'])],
            {
                'name': sensor['name'], 'sensor_code': sensor['sensor_code'], 'coletor_id': coletor_id,
                'area_id': area_id, 'measurement_type_id': measurement_type_id, 'protocolo_origem': '4-20ma',
            },
        )
    return {
        'partner_id': partner_id, 'site_id': site_id, 'hub_id': hub_id,
        'area_id': area_id, 'coletor_id': coletor_id,
    }


def main():
    parser = argparse.ArgumentParser(description='Provisiona o cenário simulado no Odoo (idempotente)')
    parser.add_argument('--odoo-url', default='http://localhost:8189', dest='odoo_url')
    parser.add_argument('--odoo-db', default='sentinela', dest='odoo_db')
    parser.add_argument('--odoo-usuario', default='admin', dest='odoo_usuario')
    parser.add_argument('--odoo-senha', default='admin', dest='odoo_senha')
    args = parser.parse_args()
    cliente = odoo_cliente.conectar(args.odoo_url, args.odoo_db, args.odoo_usuario, args.odoo_senha)
    resultado = provisionar(cliente)
    print(f"Provisionado: {resultado}")


if __name__ == '__main__':
    main()
