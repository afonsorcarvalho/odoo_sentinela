import argparse
import random
import time
from datetime import datetime, timezone

from . import timescale

# sensor_id aqui TEM que bater exatamente com sensor_code em Odoo
# (sensor_monitor.sensor) — é essa string que o SSE (/sensores/{code}/live)
# usa pra rotear a notificação pro assinante certo.
SENSORES = [
    ('SNR-EXP-TEMP-01', 'AREA-EXPURGO', 'temperatura', 'C', (18, 22)),
    ('SNR-EXP-PRES-01', 'AREA-EXPURGO', 'pressao_diferencial', 'Pa', (-15, -2.5)),
    ('SNR-PRE-TEMP-01', 'AREA-PREPARO', 'temperatura', 'C', (20, 24)),
    ('SNR-PRE-UMID-01', 'AREA-PREPARO', 'umidade_relativa', '%UR', (40, 60)),
    ('SNR-EST-TEMP-01', 'AREA-ESTERIL', 'temperatura', 'C', (20, 24)),
    ('SNR-EST-PRES-01', 'AREA-ESTERIL', 'pressao_diferencial', 'Pa', (2.5, 15)),
    ('SNR-ARS-TEMP-01', 'AREA-ARSENAL', 'temperatura', 'C', (18, 26)),
    ('SNR-ARS-UMID-01', 'AREA-ARSENAL', 'umidade_relativa', '%UR', (35, 65)),
]


def gerar_leitura(sensor_id, area_id, tipo_medida, unidade, faixa):
    meio = (faixa[0] + faixa[1]) / 2
    ruido = (faixa[1] - faixa[0]) * 0.05
    valor = round(meio + random.gauss(0, ruido), 2)
    return {
        'timestamp': datetime.now(timezone.utc),
        'sensor_id': sensor_id,
        'area_id': area_id,
        'tipo_medida': tipo_medida,
        'valor': valor,
        'unidade': unidade,
        'protocolo_origem': '4-20ma',
        'status_leitura': 'ok',
    }


def main():
    parser = argparse.ArgumentParser(description='Gera leituras continuas (loop) direto no TimescaleDB, pra demo ao vivo do frontend')
    parser.add_argument('--dsn', default='postgresql://sentinela:sentinela@localhost:5433/sentinela')
    parser.add_argument('--site-id', default='SITE-DEMO-01')
    parser.add_argument('--coletor-id', default='COL-DEMO-01')
    parser.add_argument('--intervalo', type=float, default=3.0)
    args = parser.parse_args()

    conn = timescale.conectar(args.dsn)
    print(f"Gerando leituras a cada {args.intervalo}s pra {len(SENSORES)} sensores. Ctrl+C pra parar.")
    try:
        while True:
            leituras = [gerar_leitura(*s) for s in SENSORES]
            n = timescale.inserir_leituras(conn, args.site_id, args.coletor_id, leituras)
            print(f"{datetime.now().strftime('%H:%M:%S')} — {n} leituras inseridas")
            time.sleep(args.intervalo)
    except KeyboardInterrupt:
        print("Parado.")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
