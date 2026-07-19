import argparse
import math
import random
from datetime import datetime, timedelta, timezone

from . import timescale
from .simulador_continuo import SENSORES

SITE_ID = 'SITE-DEMO-01'
COLETOR_ID = 'COL-DEMO-01'


def _gerar_leitura_historica(sensor_id, area_id, tipo_medida, unidade, faixa, ts):
    meio = (faixa[0] + faixa[1]) / 2
    amplitude = (faixa[1] - faixa[0]) / 3
    ruido = (faixa[1] - faixa[0]) * 0.05
    fase_horas = ts.timestamp() / 3600
    valor = round(meio + amplitude * math.sin(fase_horas / 12) + random.gauss(0, ruido), 2)
    return {
        'timestamp': ts, 'sensor_id': sensor_id, 'area_id': area_id, 'tipo_medida': tipo_medida,
        'valor': valor, 'unidade': unidade, 'protocolo_origem': '4-20ma', 'status_leitura': 'ok',
    }


def gerar_historico(dias, intervalo_minutos, agora=None):
    agora = agora or datetime.now(timezone.utc)
    inicio = agora - timedelta(days=dias)
    fim = agora - timedelta(hours=1)
    passo = timedelta(minutes=intervalo_minutos)

    leituras = []
    ts = inicio
    while ts < fim:
        for sensor_id, area_id, tipo_medida, unidade, faixa in SENSORES:
            leituras.append(_gerar_leitura_historica(sensor_id, area_id, tipo_medida, unidade, faixa, ts))
        ts += passo
    return leituras


def limpar_backfill(conn, dias, agora=None):
    agora = agora or datetime.now(timezone.utc)
    inicio = agora - timedelta(days=dias)
    fim = agora - timedelta(hours=1)
    sensor_ids = [s[0] for s in SENSORES]
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM sensor_reading WHERE sensor_id = ANY(%s) AND time >= %s AND time < %s",
            (sensor_ids, inicio, fim),
        )
    conn.commit()


def refrescar_agregados(conn, dias, agora=None):
    agora = agora or datetime.now(timezone.utc)
    inicio = agora - timedelta(days=dias, hours=1)
    fim = agora + timedelta(hours=1)
    # refresh_continuous_aggregate() do Timescale so' roda fora de bloco de
    # transacao — autocommit so' pra essa chamada, restaurado em seguida
    # (mesmo padrao de api/tests/test_historico.py).
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CALL refresh_continuous_aggregate('sensor_reading_hourly', %s, %s)", (inicio, fim))
            cur.execute("CALL refresh_continuous_aggregate('sensor_reading_daily', %s, %s)", (inicio, fim))
    finally:
        conn.autocommit = False


def main():
    parser = argparse.ArgumentParser(
        description='Backfill de historico sintetico pros sensores da demo + refresh manual dos continuous aggregates '
                     '(a policy automatica do Timescale nao alcanca dados inseridos retroativamente)',
    )
    parser.add_argument('--dsn', default='postgresql://sentinela:sentinela@localhost:5433/sentinela')
    parser.add_argument('--dias', type=int, default=30)
    parser.add_argument('--intervalo-minutos', type=int, default=15)
    args = parser.parse_args()

    conn = timescale.conectar(args.dsn)
    try:
        limpar_backfill(conn, args.dias)
        leituras = gerar_historico(args.dias, args.intervalo_minutos)
        total = timescale.inserir_leituras(conn, SITE_ID, COLETOR_ID, leituras)
        print(f"{total} leituras historicas inseridas ({args.dias} dias, {len(SENSORES)} sensores, passo {args.intervalo_minutos}min)")
        refrescar_agregados(conn, args.dias)
        print("Continuous aggregates (hourly/daily) atualizados sobre o range do backfill")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
