"""Agregacao de leituras por bucket (hora/dia/mes) no fuso local, para o relatorio de periodo."""
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

TZ = 'America/Sao_Paulo'

# Lista branca: unidade do date_trunc e passo da serie (nunca vem do usuario).
_UNIDADES = {
    'hora': ('hour', '1 hour'),
    'dia': ('day', '1 day'),
    'mes': ('month', '1 month'),
}


def granularidade(inicio: date, fim: date) -> Literal['hora', 'dia', 'mes']:
    if inicio == fim:
        return 'hora'
    if (fim - inicio).days + 1 <= 62:
        return 'dia'
    return 'mes'


def intervalo_utc(inicio: date, fim: date) -> tuple[datetime, datetime]:
    """[inicio 00:00 local, (fim+1) 00:00 local) como datetimes aware em UTC."""
    tz = ZoneInfo(TZ)
    ini = datetime.combine(inicio, time.min, tzinfo=tz).astimezone(timezone.utc)
    fim_excl = datetime.combine(fim + timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc)
    return ini, fim_excl


def _limites_serie(inicio: date, fim: date, gran: str) -> tuple[datetime, datetime]:
    """Primeiro e ultimo bucket (naive, hora local)."""
    if gran == 'hora':
        base = datetime.combine(inicio, time.min)
        return base, base + timedelta(hours=23)
    if gran == 'dia':
        return datetime.combine(inicio, time.min), datetime.combine(fim, time.min)
    return datetime(inicio.year, inicio.month, 1), datetime(fim.year, fim.month, 1)


_SQL = """
WITH serie AS (
    SELECT generate_series(%(primeiro)s::timestamp, %(ultimo)s::timestamp, %(passo)s::interval) AS local_ts
),
agg AS (
    SELECT date_trunc(%(unidade)s, time AT TIME ZONE %(tz)s) AS local_ts,
           avg(valor)  FILTER (WHERE status_leitura = 'ok') AS v_avg,
           min(valor)  FILTER (WHERE status_leitura = 'ok') AS v_min,
           max(valor)  FILTER (WHERE status_leitura = 'ok') AS v_max,
           count(*)    FILTER (WHERE status_leitura = 'ok') AS n_ok,
           count(*)    FILTER (WHERE status_leitura <> 'ok') AS n_falha
    FROM sensor_reading
    WHERE sensor_id = %(sensor)s
      AND site_id = ANY(%(sites)s)
      AND time >= %(ini)s AND time < %(fim)s
    GROUP BY 1
)
SELECT s.local_ts AT TIME ZONE %(tz)s AS bucket,
       a.v_avg, a.v_min, a.v_max,
       COALESCE(a.n_ok, 0), COALESCE(a.n_falha, 0)
FROM serie s LEFT JOIN agg a ON a.local_ts = s.local_ts
ORDER BY s.local_ts
"""


def buscar_buckets(conn, sensor_code: str, inicio: date, fim: date, gran: str,
                   sites_permitidos: list[str]) -> list[dict]:
    unidade, passo = _UNIDADES[gran]  # KeyError para gran invalida
    primeiro, ultimo = _limites_serie(inicio, fim, gran)
    ini_utc, fim_utc = intervalo_utc(inicio, fim)
    with conn.cursor() as cur:
        cur.execute(_SQL, {
            'primeiro': primeiro, 'ultimo': ultimo, 'passo': passo, 'unidade': unidade,
            'tz': TZ, 'sensor': sensor_code, 'sites': list(sites_permitidos),
            'ini': ini_utc, 'fim': fim_utc,
        })
        linhas = cur.fetchall()
    resultado = []
    for bucket, v_avg, v_min, v_max, n_ok, n_falha in linhas:
        estado = 'ok' if n_ok > 0 else ('falha_instrumento' if n_falha > 0 else 'sem_dados')
        resultado.append({
            'bucket': bucket, 'avg': v_avg, 'min': v_min, 'max': v_max,
            'n_ok': n_ok, 'n_falha': n_falha, 'estado': estado,
        })
    return resultado
