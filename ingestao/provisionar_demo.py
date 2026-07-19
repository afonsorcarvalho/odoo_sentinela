import argparse

from . import odoo_cliente

PARTNER_NAME = 'Cliente Demo'
SITE_CODE = 'SITE-DEMO-01'
HUB_CODE = 'HUB-DEMO-01'
COLETOR_CODE = 'COL-DEMO-01'

AREAS = [
    {
        'area_code': 'AREA-EXPURGO', 'name': 'Expurgo', 'category_code': 'EXPURGO',
        'sensores': [
            {'sensor_code': 'SNR-EXP-TEMP-01', 'name': 'Temperatura Expurgo', 'measurement_type_code': 'temperatura',
             'unidade': 'C', 'limite_min': 18, 'limite_max': 22, 'is_padrao': True},
            {'sensor_code': 'SNR-EXP-PRES-01', 'name': 'Pressão Diferencial Expurgo', 'measurement_type_code': 'pressao_diferencial',
             'unidade': 'Pa', 'limite_min': -15, 'limite_max': -2.5, 'is_padrao': True},
        ],
    },
    {
        'area_code': 'AREA-PREPARO', 'name': 'Preparo', 'category_code': 'PREPARO_ESTERILIZACAO',
        'sensores': [
            {'sensor_code': 'SNR-PRE-TEMP-01', 'name': 'Temperatura Preparo', 'measurement_type_code': 'temperatura',
             'unidade': 'C', 'limite_min': 20, 'limite_max': 24, 'is_padrao': True},
            {'sensor_code': 'SNR-PRE-UMID-01', 'name': 'Umidade Preparo', 'measurement_type_code': 'umidade_relativa',
             'unidade': '%UR', 'limite_min': 40, 'limite_max': 60, 'is_padrao': False,
             'justificativa': 'Faixa operacional definida localmente — sem valor padrão RDC15 para umidade nesta área'},
        ],
    },
    {
        'area_code': 'AREA-ESTERIL', 'name': 'Esterilização', 'category_code': 'PREPARO_ESTERILIZACAO',
        'sensores': [
            {'sensor_code': 'SNR-EST-TEMP-01', 'name': 'Temperatura Esterilização', 'measurement_type_code': 'temperatura',
             'unidade': 'C', 'limite_min': 20, 'limite_max': 24, 'is_padrao': True},
            {'sensor_code': 'SNR-EST-PRES-01', 'name': 'Pressão Diferencial Esterilização', 'measurement_type_code': 'pressao_diferencial',
             'unidade': 'Pa', 'limite_min': 2.5, 'limite_max': 15, 'is_padrao': True},
        ],
    },
    {
        'area_code': 'AREA-ARSENAL', 'name': 'Arsenal', 'category_code': 'ARSENAL',
        'sensores': [
            {'sensor_code': 'SNR-ARS-TEMP-01', 'name': 'Temperatura Arsenal', 'measurement_type_code': 'temperatura',
             'unidade': 'C', 'limite_min': 18, 'limite_max': 26, 'is_padrao': False,
             'justificativa': 'Faixa operacional definida localmente — sem valor padrão RDC15 para Arsenal'},
            {'sensor_code': 'SNR-ARS-UMID-01', 'name': 'Umidade Arsenal', 'measurement_type_code': 'umidade_relativa',
             'unidade': '%UR', 'limite_min': 35, 'limite_max': 65, 'is_padrao': False,
             'justificativa': 'Faixa operacional definida localmente — sem valor padrão RDC15 para umidade nesta área'},
        ],
    },
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
        {'name': 'Hospital Demonstração — CME Central', 'partner_id': partner_id, 'site_code': SITE_CODE, 'vertical': 'cme_hospitalar'},
    )
    hub_id = _buscar_ou_criar(
        cliente, 'sensor_monitor.hub', [('hub_code', '=', HUB_CODE)],
        {'name': 'Hub Demo', 'site_id': site_id, 'hub_code': HUB_CODE},
    )
    coletor_id = _buscar_ou_criar(
        cliente, 'sensor_monitor.coletor', [('coletor_code', '=', COLETOR_CODE)],
        {'name': 'Coletor Demo', 'hub_id': hub_id, 'coletor_code': COLETOR_CODE, 'tipo': 'esp32_wifi'},
    )

    # Arsenal não tem categoria de área pré-cadastrada (data/area_category_data.xml
    # só tem EXPURGO/PREPARO_ESTERILIZACAO/DESINFECCAO_QUIMICA) — cria sob demanda.
    arsenal_category_id = _buscar_ou_criar(
        cliente, 'sensor_monitor.area.category', [('code', '=', 'ARSENAL')],
        {'name': 'Arsenal', 'code': 'ARSENAL', 'vertical': 'cme_hospitalar'},
    )
    categorias_por_code = {'ARSENAL': arsenal_category_id}

    area_ids = {}
    for area in AREAS:
        category_code = area['category_code']
        if category_code not in categorias_por_code:
            categorias_por_code[category_code] = _buscar_id(
                cliente, 'sensor_monitor.area.category', [('code', '=', category_code)],
            )
        area_id = _buscar_ou_criar(
            cliente, 'sensor_monitor.area', [('area_code', '=', area['area_code'])],
            {
                'name': area['name'], 'site_id': site_id,
                'area_category_id': categorias_por_code[category_code], 'area_code': area['area_code'],
            },
        )
        area_ids[area['area_code']] = area_id

        for sensor in area['sensores']:
            measurement_type_id = _buscar_id(
                cliente, 'sensor_monitor.measurement.type', [('code', '=', sensor['measurement_type_code'])],
            )
            sensor_id = _buscar_ou_criar(
                cliente, 'sensor_monitor.sensor', [('sensor_code', '=', sensor['sensor_code'])],
                {
                    'name': sensor['name'], 'sensor_code': sensor['sensor_code'], 'coletor_id': coletor_id,
                    'area_id': area_id, 'measurement_type_id': measurement_type_id,
                    'protocolo_origem': '4-20ma', 'unidade': sensor['unidade'],
                },
            )
            threshold_valores = {
                'sensor_id': sensor_id,
                'limite_min': sensor['limite_min'],
                'limite_max': sensor['limite_max'],
                'is_valor_padrao_regulatorio': sensor['is_padrao'],
            }
            if not sensor['is_padrao']:
                threshold_valores['justificativa_desvio'] = sensor['justificativa']
            _buscar_ou_criar(
                cliente, 'sensor_monitor.alarm.threshold', [('sensor_id', '=', sensor_id)], threshold_valores,
            )

    return {'site_id': site_id, 'hub_id': hub_id, 'coletor_id': coletor_id, 'area_ids': area_ids}


def main():
    parser = argparse.ArgumentParser(description='Provisiona o cenário de demonstração (4 áreas, sensores e thresholds) no Odoo (idempotente)')
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
