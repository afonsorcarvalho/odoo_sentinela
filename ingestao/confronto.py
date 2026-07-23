"""Confronto de veracidade (§5.2): Timescale (cache) vs arquivo assinado (verdade).

Parte 1 — assinaturas: reusa validador.validar_arquivo (hdr_sig + sig por linha).
Parte 2 — valores: cada linha verificada do arquivo tem que bater com a linha
correspondente no Timescale, por (sensor_id, timestamp_utc). Divergência em
qualquer parte = alerta de auditoria.
"""
import argparse
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def confrontar_arquivo(caminho, registro_path, conn, coletor_esperado=None, data_esperada=None):
    rv = validador.validar_arquivo(caminho, registro_path)

    # Parte 1: assinaturas
    assinaturas_ok = rv.status_validacao in ('valido', 'incompleto')
    arquivo_nao_fechado = rv.status_validacao == 'incompleto'
    if not assinaturas_ok:
        return ResultadoConfronto(
            coletor_id=rv.coletor_id, data_referencia=rv.data_referencia,
            assinaturas_ok=False, valores_ok=False, arquivo_nao_fechado=False,
            motivo=f'assinatura inválida: {rv.motivo_rejeicao}')

    # Anti-substituição: um arquivo válido e corretamente assinado, mas de OUTRO
    # coletor/data/tipo, colocado no lugar do arquivo pedido, não pode passar por
    # confronto "limpo" — ele nunca é comparado contra os dados do coletor real.
    if coletor_esperado is not None and (
            rv.coletor_id != coletor_esperado
            or rv.data_referencia != data_esperada
            or rv.tipo_arquivo != 'leituras'):
        return ResultadoConfronto(
            coletor_id=rv.coletor_id, data_referencia=rv.data_referencia,
            assinaturas_ok=False, valores_ok=False, arquivo_nao_fechado=False,
            motivo='identidade do arquivo diverge do solicitado (coletor/data/tipo)')

    # Parte 2: value-match contra o Timescale
    linhas = rv.leituras
    if not linhas:
        if conn is not None and rv.data_referencia:
            # Dia assinado sem nenhuma leitura: mesmo sem chaves de arquivo pra
            # comparar, qualquer row no Timescale pro dia é fabricada. Janela é o
            # dia LOCAL do coletor (data_referencia + timezone_offset do header),
            # não o dia UTC ingênuo — coletores rodam em fuso local (ex.: -03:00),
            # e um dia UTC ingênuo erra a fronteira: uma leitura injetada perto da
            # meia-noite local cai fora da janela e escapa do count-match.
            #
            # timezone_offset vazio/ausente NÃO pode desligar o count-match (isso
            # seria fail-open: um hub mal configurado que grava offset vazio
            # deixaria dias vazios sem nenhuma checagem). Cai pra UTC ('+00:00')
            # como fallback seguro — pior caso é uma fronteira de dia levemente
            # errada perto da meia-noite, não a ausência total de detecção. Um
            # offset presente porém malformado (ex.: '-0300' sem ':') faz
            # fromisoformat levantar — falha ALTA e ruidosa, não silenciosa.
            offset = rv.timezone_offset if (rv.timezone_offset and rv.timezone_offset.strip()) else '+00:00'
            ts_inicio = datetime.fromisoformat(
                rv.data_referencia + 'T00:00:00' + offset)
            ts_fim = ts_inicio + timedelta(days=1)
            mapa_vazio = timescale.buscar_leituras_para_confronto(
                conn, rv.coletor_id, ts_inicio, ts_fim)
            injetadas = [{'sensor_id': s, 'timestamp': ts} for (s, ts) in mapa_vazio]
            return ResultadoConfronto(
                coletor_id=rv.coletor_id, data_referencia=rv.data_referencia,
                assinaturas_ok=True, valores_ok=(not injetadas),
                arquivo_nao_fechado=arquivo_nao_fechado, injetadas_timescale=injetadas)
        # Sem conexão ou sem data_referencia no header: não dá pra montar a janela
        # (nem sequer o fallback UTC) com segurança — não fazemos count-match.
        # Não é brecha de ataque: data_referencia está sob hdr_sig (assinatura do
        # header, já verificada em assinaturas_ok acima). `valores_ok=True` aqui
        # reflete "não deu pra checar" apenas para o caso sem conexão (conn=None,
        # ex.: chamador sem acesso ao Timescale) ou headers pré-v2/malformados que
        # nem chegariam a passar por assinaturas_ok em produção.
        return ResultadoConfronto(
            coletor_id=rv.coletor_id, data_referencia=rv.data_referencia,
            assinaturas_ok=True, valores_ok=True,
            arquivo_nao_fechado=arquivo_nao_fechado, injetadas_timescale=[])

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
    # SEMPRE ativo, mesmo em arquivo incompleto (footerless): a janela de busca é
    # [min_ts, max_ts+1s) onde max_ts é a ÚLTIMA linha verificada por cadeia — uma
    # cauda legítima não gravada (crash) fica DEPOIS de max_ts, fora da janela.
    # Tudo que aparece dentro de [min_ts, max_ts] e não tem par no arquivo é
    # injeção comprovada, arquivo selado ou não.
    injetadas = [{'sensor_id': s, 'timestamp': ts}
                 for (s, ts) in mapa if (s, ts) not in chaves_arquivo]

    return ResultadoConfronto(
        coletor_id=rv.coletor_id, data_referencia=rv.data_referencia,
        assinaturas_ok=True, valores_ok=(not divergencias and not injetadas),
        arquivo_nao_fechado=arquivo_nao_fechado, divergencias=divergencias,
        injetadas_timescale=injetadas)


def confrontar_periodo(diretorio_arquivos, coletor_id, datas, registro_path, conn):
    resultados = []
    for data in datas:
        caminho = Path(diretorio_arquivos) / f"{data}_leituras.txt"
        if not caminho.exists():
            resultados.append(ResultadoConfronto(
                coletor_id=coletor_id, data_referencia=data,
                assinaturas_ok=False, valores_ok=False, arquivo_nao_fechado=False,
                motivo='arquivo ausente no acervo (fonte da verdade faltando)'))
            continue
        resultados.append(confrontar_arquivo(
            str(caminho), registro_path, conn,
            coletor_esperado=coletor_id, data_esperada=data))
    return resultados


def _datas_entre(de, ate):
    from datetime import date
    d0, d1 = date.fromisoformat(de), date.fromisoformat(ate)
    dias, atual = [], d0
    while atual <= d1:
        dias.append(atual.isoformat())
        atual += timedelta(days=1)
    return dias


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Confronto de veracidade Timescale vs arquivos assinados (§5.2)')
    parser.add_argument('--diretorio', required=True, help='dir do acervo do coletor')
    parser.add_argument('--coletor', required=True)
    parser.add_argument('--de', required=True, help='YYYY-MM-DD')
    parser.add_argument('--ate', required=True, help='YYYY-MM-DD')
    parser.add_argument('--registro', default='ingestao/coletores_conhecidos.json')
    parser.add_argument('--dsn', default='postgresql://sentinela:sentinela@localhost:5433/sentinela')
    args = parser.parse_args(argv)

    conn = timescale.conectar(args.dsn)
    try:
        resultados = confrontar_periodo(
            args.diretorio, args.coletor, _datas_entre(args.de, args.ate),
            args.registro, conn)
    finally:
        conn.close()

    if not resultados:
        print(f"[ERRO] período vazio ou invertido (--de {args.de} --ate {args.ate}): "
              f"nenhum dia a confrontar — gate de auditoria não pode dar all-clear "
              f"silencioso sobre um range vazio.")
        return 2

    houve_alerta = False
    for r in resultados:
        alerta = (not r.assinaturas_ok) or (not r.valores_ok)
        houve_alerta = houve_alerta or alerta
        marca = 'ALERTA' if alerta else 'ok'
        extra = f" motivo={r.motivo}" if r.motivo else ''
        extra += f" divergencias={len(r.divergencias)}" if r.divergencias else ''
        extra += f" injetadas={len(r.injetadas_timescale)}" if r.injetadas_timescale else ''
        extra += ' (arquivo_nao_fechado)' if r.arquivo_nao_fechado else ''
        print(f"[{marca}] {r.coletor_id} {r.data_referencia} "
              f"assinaturas={r.assinaturas_ok} valores={r.valores_ok}{extra}")

    return 1 if houve_alerta else 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
