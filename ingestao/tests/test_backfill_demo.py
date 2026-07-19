from datetime import datetime, timedelta, timezone

from ingestao import timescale, backfill_demo

DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'


def _limpar_todos_sensores(conn):
    sensor_ids = [s[0] for s in backfill_demo.SENSORES]
    with conn.cursor() as cur:
        cur.execute("DELETE FROM sensor_reading WHERE sensor_id = ANY(%s)", (sensor_ids,))
    conn.commit()


def test_gerar_historico_cobre_todos_sensores_dentro_do_range_pedido():
    agora = datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)
    leituras = backfill_demo.gerar_historico(dias=2, intervalo_minutos=60, agora=agora)

    sensor_ids_esperados = {s[0] for s in backfill_demo.SENSORES}
    assert {l['sensor_id'] for l in leituras} == sensor_ids_esperados

    por_sensor = [l for l in leituras if l['sensor_id'] == backfill_demo.SENSORES[0][0]]
    # janela meia-aberta [agora-2d, agora-1h), passo de 1h -> 47 pontos
    assert len(por_sensor) == 47
    assert all(l['timestamp'] >= agora - timedelta(days=2) for l in por_sensor)
    assert all(l['timestamp'] < agora - timedelta(hours=1) for l in por_sensor)
    # dentro da faixa configurada do sensor (com folga pro ruido gaussiano)
    faixa = backfill_demo.SENSORES[0][4]
    margem = (faixa[1] - faixa[0]) * 0.5
    assert all(faixa[0] - margem <= l['valor'] <= faixa[1] + margem for l in por_sensor)


def test_limpar_backfill_remove_so_o_range_do_backfill_preserva_fora_dele():
    conn = timescale.conectar(DSN)
    _limpar_todos_sensores(conn)
    agora = datetime.now(timezone.utc)
    sensor_id = backfill_demo.SENSORES[0][0]
    try:
        dentro = {
            'timestamp': agora - timedelta(days=1), 'sensor_id': sensor_id,
            'area_id': backfill_demo.SENSORES[0][1], 'tipo_medida': backfill_demo.SENSORES[0][2],
            'valor': 20.0, 'unidade': backfill_demo.SENSORES[0][3],
            'protocolo_origem': '4-20ma', 'status_leitura': 'ok',
        }
        fora = {**dentro, 'timestamp': agora - timedelta(minutes=10)}  # dentro da ultima 1h, fora do range do backfill
        timescale.inserir_leituras(conn, 'SITE-DEMO-01', 'COL-DEMO-01', [dentro, fora])

        backfill_demo.limpar_backfill(conn, dias=30, agora=agora)

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM sensor_reading WHERE sensor_id = %s", (sensor_id,))
            (restantes,) = cur.fetchone()
        assert restantes == 1  # so' a leitura 'fora' (ultima 1h) sobrevive
    finally:
        _limpar_todos_sensores(conn)
        # Refresh aggregates to clear any materialized rows from the continuous aggregate
        backfill_demo.refrescar_agregados(conn, dias=30, agora=agora)
        conn.close()


def test_refrescar_agregados_materializa_bucket_horario_para_o_range_do_backfill():
    conn = timescale.conectar(DSN)
    _limpar_todos_sensores(conn)
    agora = datetime.now(timezone.utc)
    sensor_id = backfill_demo.SENSORES[0][0]
    try:
        leitura = {
            'timestamp': agora - timedelta(days=5), 'sensor_id': sensor_id,
            'area_id': backfill_demo.SENSORES[0][1], 'tipo_medida': backfill_demo.SENSORES[0][2],
            'valor': 21.5, 'unidade': backfill_demo.SENSORES[0][3],
            'protocolo_origem': '4-20ma', 'status_leitura': 'ok',
        }
        timescale.inserir_leituras(conn, 'SITE-DEMO-01', 'COL-DEMO-01', [leitura])

        backfill_demo.refrescar_agregados(conn, dias=30, agora=agora)

        with conn.cursor() as cur:
            cur.execute(
                "SELECT avg(valor_avg) FROM sensor_reading_hourly WHERE sensor_id = %s "
                "AND bucket = date_trunc('hour', %s::timestamptz)",
                (sensor_id, leitura['timestamp']),
            )
            resultado = cur.fetchone()
        assert resultado is not None and resultado[0] == 21.5
    finally:
        _limpar_todos_sensores(conn)
        # Refresh aggregates to clear any materialized rows from the continuous aggregate
        # (reading was 5 days old, so dias=7 safely covers that range)
        backfill_demo.refrescar_agregados(conn, dias=7, agora=agora)
        conn.close()
