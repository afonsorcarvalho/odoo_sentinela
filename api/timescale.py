TABELAS_AGREGADO = {'sensor_reading_hourly', 'sensor_reading_daily'}


def buscar_raw(conn, sensor_code, desde, sites_permitidos):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT time, valor FROM sensor_reading "
            "WHERE sensor_id = %s AND time >= %s AND site_id = ANY(%s) ORDER BY time",
            (sensor_code, desde, sites_permitidos),
        )
        linhas = cur.fetchall()
    return [{'time': linha[0], 'valor': linha[1]} for linha in linhas]


def buscar_agregado(conn, sensor_code, tabela, desde, sites_permitidos):
    if tabela not in TABELAS_AGREGADO:
        raise ValueError(f"tabela agregada desconhecida: {tabela}")
    with conn.cursor() as cur:
        # Seguro so' porque sensor_code tem unique() global (sensor.py) -- se isso
        # virar unique por site/empresa no futuro, este LIMIT 1 vira vetor de leak cross-tenant.
        cur.execute("SELECT site_id FROM sensor_reading WHERE sensor_id = %s LIMIT 1", (sensor_code,))
        linha_site = cur.fetchone()
    if linha_site is None or linha_site[0] not in sites_permitidos:
        return []
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT bucket, valor_min, valor_max, valor_avg FROM {tabela} "
            "WHERE sensor_id = %s AND bucket >= %s ORDER BY bucket",
            (sensor_code, desde),
        )
        linhas = cur.fetchall()
    return [{'bucket': linha[0], 'min': linha[1], 'max': linha[2], 'avg': linha[3]} for linha in linhas]
