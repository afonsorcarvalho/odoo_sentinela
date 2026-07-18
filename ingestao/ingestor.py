import argparse
from dataclasses import dataclass

from . import timescale, validador


@dataclass
class ResultadoIngestao:
    status_validacao: str
    motivo_rejeicao: str
    total_linhas: int
    total_gravado: int


def ingerir_arquivo(caminho, registro_path, dsn, site_id):
    resultado_validacao = validador.validar_arquivo(caminho, registro_path)
    if resultado_validacao.status_validacao != 'valido':
        return ResultadoIngestao(
            status_validacao=resultado_validacao.status_validacao,
            motivo_rejeicao=resultado_validacao.motivo_rejeicao,
            total_linhas=resultado_validacao.total_linhas,
            total_gravado=0,
        )
    conn = timescale.conectar(dsn)
    try:
        total_gravado = timescale.inserir_leituras(
            conn, site_id, resultado_validacao.coletor_id, resultado_validacao.leituras,
        )
    finally:
        conn.close()
    return ResultadoIngestao(
        status_validacao='valido',
        motivo_rejeicao=None,
        total_linhas=resultado_validacao.total_linhas,
        total_gravado=total_gravado,
    )


def main():
    parser = argparse.ArgumentParser(description='Ingestão de arquivo de leituras do coletor simulado')
    parser.add_argument('--arquivo', required=True)
    parser.add_argument('--registro', default='ingestao/coletores_conhecidos.json')
    parser.add_argument('--site-id', required=True, dest='site_id')
    parser.add_argument('--dsn', default='postgresql://sentinela:sentinela@localhost:5433/sentinela')
    args = parser.parse_args()
    resultado = ingerir_arquivo(args.arquivo, args.registro, args.dsn, args.site_id)
    print(
        f"status={resultado.status_validacao} total_linhas={resultado.total_linhas} "
        f"total_gravado={resultado.total_gravado} motivo={resultado.motivo_rejeicao}"
    )


if __name__ == '__main__':
    main()
