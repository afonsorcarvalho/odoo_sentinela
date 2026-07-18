from ingestao import timescale

DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'


def _limpar(site_id):
    conn = timescale.conectar(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sensor_reading WHERE site_id = %s", (site_id,))
        conn.commit()
    finally:
        conn.close()


def test_conectar_e_inserir_leituras():
    site_id = 'SITE-TEST-TIMESCALE'
    _limpar(site_id)
    conn = timescale.conectar(DSN)
    leituras = [
        {
            'timestamp': '2026-07-18T00:00:00-03:00',
            'sensor_id': 'SNR-TEST-001',
            'area_id': 'EXPURGO',
            'tipo_medida': 'temperatura',
            'valor': 19.9,
            'unidade': 'C',
            'protocolo_origem': '4-20mA',
            'status_leitura': 'ok',
        },
    ]
    try:
        total = timescale.inserir_leituras(conn, site_id, 'COL-TEST-001', leituras)
        assert total == 1
        with conn.cursor() as cur:
            cur.execute(
                "SELECT sensor_id, valor FROM sensor_reading WHERE site_id = %s", (site_id,),
            )
            linhas = cur.fetchall()
        assert linhas == [('SNR-TEST-001', 19.9)]
    finally:
        conn.close()
        _limpar(site_id)


def test_inserir_leituras_vazio_retorna_zero():
    conn = timescale.conectar(DSN)
    try:
        total = timescale.inserir_leituras(conn, 'SITE-TEST-VAZIO', 'COL-TEST-001', [])
        assert total == 0
    finally:
        conn.close()
