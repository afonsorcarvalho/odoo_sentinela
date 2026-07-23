from datetime import timezone

import psycopg2
from psycopg2.extras import execute_values


def conectar(dsn):
    return psycopg2.connect(dsn)


def inserir_leituras(conn, site_id, coletor_id, leituras,
                     cliente_id=None, pubkey_fingerprint=None, file_hash=None, ts_ingestao=None):
    if not leituras:
        return 0
    valores = [
        (
            leitura['timestamp'], site_id, coletor_id, leitura['sensor_id'],
            leitura['area_id'], leitura['tipo_medida'], leitura['valor'], leitura['unidade'],
            leitura['protocolo_origem'], leitura['status_leitura'],
            cliente_id, pubkey_fingerprint, file_hash, ts_ingestao,
        )
        for leitura in leituras
    ]
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO sensor_reading
                (time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade,
                 protocolo_origem, status_leitura, cliente_id, pubkey_fingerprint, file_hash, ts_ingestao)
            VALUES %s
            ON CONFLICT (sensor_id, "time", site_id) DO NOTHING
            """,
            valores,
        )
    conn.commit()
    return len(valores)


def buscar_leituras_para_confronto(conn, coletor_id, ts_inicio, ts_fim):
    """Devolve {(sensor_id, ts_utc_iso): valor} das leituras de um coletor no
    intervalo [ts_inicio, ts_fim). A chave usa o timestamp em UTC ISO para casar
    com o timestamp do arquivo convertido para UTC."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT sensor_id, time, valor
            FROM sensor_reading
            WHERE coletor_id = %s AND time >= %s AND time < %s
            """,
            (coletor_id, ts_inicio, ts_fim),
        )
        linhas = cur.fetchall()
    return {
        (sensor_id, time.astimezone(timezone.utc).isoformat()): valor
        for sensor_id, time, valor in linhas
    }
