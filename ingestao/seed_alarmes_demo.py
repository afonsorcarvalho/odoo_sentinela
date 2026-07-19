import argparse
from datetime import datetime, timedelta, timezone

from . import odoo_cliente

COLETOR_CODE = 'COL-DEMO-01'

CENARIOS = [
    {
        'sensor_code': 'SNR-EXP-PRES-01', 'tipo_violacao': 'abaixo_limite',
        'valor': -18.2, 'limite_min_vigente': -15.0, 'limite_max_vigente': None,
        'minutos_atras_deteccao': 12, 'resolvido_apos_minutos': None,
    },
    {
        'sensor_code': 'SNR-ARS-TEMP-01', 'tipo_violacao': 'acima_limite',
        'valor': 27.4, 'limite_min_vigente': None, 'limite_max_vigente': 26.0,
        'minutos_atras_deteccao': 90, 'resolvido_apos_minutos': None,
    },
    {
        'sensor_code': 'SNR-PRE-TEMP-01', 'tipo_violacao': 'acima_limite',
        'valor': 24.6, 'limite_min_vigente': None, 'limite_max_vigente': 24.0,
        'minutos_atras_deteccao': 180, 'resolvido_apos_minutos': 15,
    },
    {
        'sensor_code': 'SNR-EST-PRES-01', 'tipo_violacao': 'abaixo_limite',
        'valor': 1.8, 'limite_min_vigente': 2.5, 'limite_max_vigente': None,
        'minutos_atras_deteccao': 360, 'resolvido_apos_minutos': 20,
    },
]


def semear(cliente, agora=None):
    agora = agora or datetime.now(timezone.utc)
    coletor = odoo_cliente.resolver_coletor(cliente, COLETOR_CODE)
    ids = []
    for i, cenario in enumerate(CENARIOS):
        hash_origem = f'seed-demo-{i}'
        existentes = odoo_cliente.executar(
            cliente, 'sensor_monitor.alarm.event', 'search',
            [('origem_arquivo_hash', '=', hash_origem)],
        )
        if existentes:
            ids.append(existentes[0])
            continue

        sensor = odoo_cliente.resolver_sensor(cliente, cenario['sensor_code'])
        ts_deteccao = agora - timedelta(minutes=cenario['minutos_atras_deteccao'])
        evento_entrada = {
            'timestamp': ts_deteccao.isoformat(),
            'valor': cenario['valor'],
            'tipo_violacao': cenario['tipo_violacao'],
            'limite_min_vigente': cenario['limite_min_vigente'],
            'limite_max_vigente': cenario['limite_max_vigente'],
        }
        evento_id = odoo_cliente.processar_entrada_alarme(
            cliente, evento_entrada, sensor['id'], sensor['area_id'], coletor['id'], hash_origem,
        )
        ids.append(evento_id)

        if cenario['resolvido_apos_minutos'] is not None:
            ts_saida = ts_deteccao + timedelta(minutes=cenario['resolvido_apos_minutos'])
            odoo_cliente.processar_saida_alarme(cliente, {'timestamp': ts_saida.isoformat()}, sensor['id'])
    return ids


def main():
    parser = argparse.ArgumentParser(
        description='Semeia alarm.event de demonstracao (idempotente) pros sensores reais da demo, '
                     'pro painel de alarmes do frontend ter dado real pra mostrar',
    )
    parser.add_argument('--odoo-url', default='http://localhost:8189', dest='odoo_url')
    parser.add_argument('--odoo-db', default='sentinela', dest='odoo_db')
    parser.add_argument('--odoo-usuario', default='admin', dest='odoo_usuario')
    parser.add_argument('--odoo-senha', default='admin', dest='odoo_senha')
    args = parser.parse_args()
    cliente = odoo_cliente.conectar(args.odoo_url, args.odoo_db, args.odoo_usuario, args.odoo_senha)
    ids = semear(cliente)
    print(f"Semeados {len(ids)} alarm.event de demo: {ids}")


if __name__ == '__main__':
    main()
