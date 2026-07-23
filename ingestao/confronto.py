"""Confronto de veracidade (§5.2): Timescale (cache) vs arquivo assinado (verdade).

Parte 1 — assinaturas: reusa validador.validar_arquivo (hdr_sig + sig por linha).
Parte 2 — valores: cada linha verificada do arquivo tem que bater com a linha
correspondente no Timescale, por (sensor_id, timestamp_utc). Divergência em
qualquer parte = alerta de auditoria.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import timescale, validador

_TOLERANCIA = 1e-6


@dataclass
class ResultadoConfronto:
    coletor_id: str
    data_referencia: str
    assinaturas_ok: bool
    valores_ok: bool
    arquivo_nao_fechado: bool
    divergencias: list = field(default_factory=list)
    injetadas_timescale: list = field(default_factory=list)  # rows sem contraparte assinada
    motivo: str = None


def _ts_utc_iso(timestamp_iso):
    dt = datetime.fromisoformat(timestamp_iso)
    # Falha ALTO em timestamp naive: astimezone() num naive assume o TZ do host,
    # o que produziria uma chave UTC dependente de locale — inaceitável num tool
    # de veracidade (falsas divergências ou omissões). O header v2 sempre grava
    # offset (timezone_offset), então o ts do arquivo é sempre aware.
    if dt.tzinfo is None:
        raise ValueError(f"timestamp sem offset (naive), não confrontável: {timestamp_iso!r}")
    return dt.astimezone(timezone.utc).isoformat()


def confrontar_arquivo(caminho, registro_path, conn):
    rv = validador.validar_arquivo(caminho, registro_path)

    # Parte 1: assinaturas
    assinaturas_ok = rv.status_validacao in ('valido', 'incompleto')
    arquivo_nao_fechado = rv.status_validacao == 'incompleto'
    if not assinaturas_ok:
        return ResultadoConfronto(
            coletor_id=rv.coletor_id, data_referencia=rv.data_referencia,
            assinaturas_ok=False, valores_ok=False, arquivo_nao_fechado=False,
            motivo=f'assinatura inválida: {rv.motivo_rejeicao}')

    # Parte 2: value-match contra o Timescale
    linhas = rv.leituras
    if not linhas:
        return ResultadoConfronto(
            coletor_id=rv.coletor_id, data_referencia=rv.data_referencia,
            assinaturas_ok=True, valores_ok=True, arquivo_nao_fechado=arquivo_nao_fechado)

    ts_chaves = [_ts_utc_iso(l['timestamp']) for l in linhas]
    ts_inicio = min(datetime.fromisoformat(k) for k in ts_chaves)
    # +1s: a query usa `time < ts_fim`; sem isso a última linha do dia escaparia.
    ts_fim = max(datetime.fromisoformat(k) for k in ts_chaves) + timedelta(seconds=1)
    mapa = timescale.buscar_leituras_para_confronto(
        conn, rv.coletor_id, ts_inicio, ts_fim)

    divergencias = []
    chaves_arquivo = set()
    for linha in linhas:
        chave = (linha['sensor_id'], _ts_utc_iso(linha['timestamp']))
        chaves_arquivo.add(chave)
        valor_ts = mapa.get(chave)
        if valor_ts is None or abs(valor_ts - linha['valor']) > _TOLERANCIA:
            divergencias.append({
                'sensor_id': linha['sensor_id'], 'timestamp': linha['timestamp'],
                'valor_arquivo': linha['valor'], 'valor_timescale': valor_ts,
            })

    # count-match reverso: rows no Timescale sem contraparte assinada = injeção.
    # Só confiável quando o arquivo está fechado (senão pode ser cauda legítima
    # que o crash não gravou no arquivo).
    injetadas = []
    if not arquivo_nao_fechado:
        injetadas = [{'sensor_id': s, 'timestamp': ts}
                     for (s, ts) in mapa if (s, ts) not in chaves_arquivo]

    return ResultadoConfronto(
        coletor_id=rv.coletor_id, data_referencia=rv.data_referencia,
        assinaturas_ok=True, valores_ok=(not divergencias and not injetadas),
        arquivo_nao_fechado=arquivo_nao_fechado, divergencias=divergencias,
        injetadas_timescale=injetadas)
