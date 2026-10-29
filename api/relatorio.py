"""Relatorio de periodo: buckets agregados, alarmes e historico de limites por sensor."""
import os
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response

from ingestao import odoo_cliente
from ingestao.timescale import conectar

from .auth import get_cliente_usuario, verificar_token
from .meta import obter_sensor, obter_threshold
from .permissions import obter_sites_permitidos
from .relatorio_dados import TZ, buscar_buckets, granularidade, intervalo_utc
from .relatorio_odoo import alarmes_periodo, alteracoes_limite, empresa_cliente, nome_emissor
from .relatorio_pdf import gerar_pdf, slug

router = APIRouter()

DSN = os.environ.get('TIMESCALE_DSN', 'postgresql://sentinela:sentinela@localhost:5433/sentinela')

MAX_SENSORES = 20
MAX_DIAS = 366


class RelatorioErro(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail


def _float(valor):
    return None if valor is None else float(valor)


def _iso_utc(dt):
    return dt.astimezone(timezone.utc).isoformat()


def _nome_site(cliente, area_code):
    areas = odoo_cliente.executar(
        cliente, 'sensor_monitor.area', 'search_read',
        [('area_code', '=', area_code)], fields=['site_id'], limit=1,
    )
    return areas[0]['site_id'][1] if areas and areas[0]['site_id'] else None


def _serializar_bucket(b, limites):
    fora = False
    if limites is not None and b['estado'] == 'ok':
        fora = bool(
            (limites['limite_max'] is not None and b['max'] > limites['limite_max'])
            or (limites['limite_min'] is not None and b['min'] < limites['limite_min'])
        )
    return {
        'bucket': b['bucket'].astimezone(ZoneInfo(TZ)).isoformat(),
        'avg': _float(b['avg']), 'min': _float(b['min']), 'max': _float(b['max']),
        'n_ok': b['n_ok'], 'n_falha': b['n_falha'], 'estado': b['estado'],
        'fora_limite': fora,
    }


def montar_relatorio(cliente, sensores: list[str], inicio: date, fim: date) -> dict:
    if fim < inicio:
        raise RelatorioErro(422, 'fim anterior ao início')
    if (fim - inicio).days + 1 > MAX_DIAS:
        raise RelatorioErro(422, f'período máximo de {MAX_DIAS} dias')
    if not sensores:
        raise RelatorioErro(422, 'informe ao menos um sensor')
    if len(sensores) > MAX_SENSORES:
        raise RelatorioErro(422, f'máximo de {MAX_SENSORES} sensores')

    # Valida todos antes de qualquer consulta pesada.
    metas = {}
    for code in sensores:
        meta = obter_sensor(cliente, code)
        if meta is None:
            raise RelatorioErro(404, f"sensor '{code}' não encontrado")
        metas[code] = meta

    sites_permitidos = obter_sites_permitidos(cliente)
    gran = granularidade(inicio, fim)
    ini_utc, fim_utc = intervalo_utc(inicio, fim)

    resultado = []
    conn = conectar(DSN)
    try:
        for code in sensores:
            meta = metas[code]
            threshold = obter_threshold(cliente, code)
            limites = None
            if threshold is not None:
                limites = {'limite_min': _float(threshold['limite_min']),
                           'limite_max': _float(threshold['limite_max'])}
            buckets = buscar_buckets(conn, code, inicio, fim, gran, sites_permitidos)
            alteracoes = [
                {'quando': _iso_utc(a['quando']), 'campo': a['campo'],
                 'de': _float(a['de']), 'para': _float(a['para'])}
                for a in alteracoes_limite(cliente, code, ini_utc)
            ]
            resultado.append({
                'sensor_code': code,
                'nome': meta['name'],
                'unidade': meta['unidade'],
                'site': _nome_site(cliente, meta['area']['area_code']),
                'limites': limites,
                'alteracoes_limite': alteracoes,
                'buckets': [_serializar_bucket(b, limites) for b in buckets],
                'alarmes': alarmes_periodo(cliente, code, ini_utc, fim_utc),
            })
    finally:
        conn.close()

    return {
        'inicio': inicio.isoformat(), 'fim': fim.isoformat(),
        'granularidade': gran, 'fuso': TZ,
        'emitido_em': datetime.now(timezone.utc).isoformat(),
        'emissor': nome_emissor(cliente),
        'sensores': resultado,
    }


def _montar_ou_http(cliente, sensores: str, inicio: date, fim: date) -> dict:
    codigos = [c.strip() for c in sensores.split(',') if c.strip()]
    try:
        return montar_relatorio(cliente, codigos, inicio, fim)
    except RelatorioErro as erro:
        raise HTTPException(status_code=erro.status_code, detail=erro.detail)


@router.get('/relatorio')
def get_relatorio(
    sensores: str,
    inicio: date,
    fim: date,
    cliente=Depends(get_cliente_usuario),
    _claims=Depends(verificar_token),
):
    return _montar_ou_http(cliente, sensores, inicio, fim)


@router.get('/relatorio.pdf')
def get_relatorio_pdf(
    sensores: str,
    inicio: date,
    fim: date,
    cliente=Depends(get_cliente_usuario),
    _claims=Depends(verificar_token),
):
    relatorio = _montar_ou_http(cliente, sensores, inicio, fim)
    nome, logo = empresa_cliente(cliente, [s['sensor_code'] for s in relatorio['sensores']])
    arquivo = f'relatorio_{slug(nome)}_{inicio.isoformat()}_{fim.isoformat()}.pdf'
    return Response(
        content=gerar_pdf(relatorio, nome, logo=logo), media_type='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="{arquivo}"'},
    )
