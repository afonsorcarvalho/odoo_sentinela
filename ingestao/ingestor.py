import argparse
from dataclasses import dataclass

from . import odoo_cliente, timescale, validador


@dataclass
class ResultadoIngestao:
    status_validacao: str
    motivo_rejeicao: str
    total_linhas: int
    total_gravado: int
    eventos_orfaos: int = 0


def _processar_leituras(dsn, info_coletor, resultado_validacao):
    conn = timescale.conectar(dsn)
    try:
        return timescale.inserir_leituras(
            conn, info_coletor['site_code'], resultado_validacao.coletor_id, resultado_validacao.leituras,
        )
    finally:
        conn.close()


def _processar_alarmes(cliente_odoo, info_coletor, resultado_validacao):
    eventos_orfaos = 0
    for evento in resultado_validacao.eventos:
        info_sensor = odoo_cliente.resolver_sensor(cliente_odoo, evento['sensor_id'])
        if evento['tipo_evento'] == 'entrada_alarme':
            odoo_cliente.processar_entrada_alarme(
                cliente_odoo, evento, info_sensor['id'], info_sensor['area_id'],
                info_coletor['id'], resultado_validacao.hash_final,
            )
        elif evento['tipo_evento'] == 'saida_alarme':
            resolvido = odoo_cliente.processar_saida_alarme(cliente_odoo, evento, info_sensor['id'])
            if resolvido is None:
                eventos_orfaos += 1
    return eventos_orfaos


def ingerir_arquivo(caminho, registro_path, dsn, cliente_odoo):
    resultado_validacao = validador.validar_arquivo(caminho, registro_path)

    try:
        info_coletor = odoo_cliente.resolver_coletor(cliente_odoo, resultado_validacao.coletor_id)
    except ValueError as exc:
        return ResultadoIngestao(
            status_validacao='invalido',
            motivo_rejeicao=str(exc),
            total_linhas=resultado_validacao.total_linhas,
            total_gravado=0,
        )

    total_gravado = 0
    eventos_orfaos = 0
    if resultado_validacao.status_validacao == 'valido':
        if resultado_validacao.tipo_arquivo == 'alarmes':
            eventos_orfaos = _processar_alarmes(cliente_odoo, info_coletor, resultado_validacao)
            total_gravado = len(resultado_validacao.eventos)
        else:
            total_gravado = _processar_leituras(dsn, info_coletor, resultado_validacao)

    odoo_cliente.escrever_ledger(
        cliente_odoo, info_coletor['id'], resultado_validacao.tipo_arquivo, resultado_validacao.data_referencia,
        resultado_validacao.status_validacao, resultado_validacao.motivo_rejeicao,
        resultado_validacao.total_linhas, resultado_validacao.hash_final, resultado_validacao.assinatura,
    )

    return ResultadoIngestao(
        status_validacao=resultado_validacao.status_validacao,
        motivo_rejeicao=resultado_validacao.motivo_rejeicao,
        total_linhas=resultado_validacao.total_linhas,
        total_gravado=total_gravado,
        eventos_orfaos=eventos_orfaos,
    )


def main():
    parser = argparse.ArgumentParser(description='Ingestão de arquivo (leituras ou alarmes) do coletor simulado')
    parser.add_argument('--arquivo', required=True)
    parser.add_argument('--registro', default='ingestao/coletores_conhecidos.json')
    parser.add_argument('--dsn', default='postgresql://sentinela:sentinela@localhost:5433/sentinela')
    parser.add_argument('--odoo-url', default='http://localhost:8189', dest='odoo_url')
    parser.add_argument('--odoo-db', default='sentinela', dest='odoo_db')
    parser.add_argument('--odoo-usuario', default='admin', dest='odoo_usuario')
    parser.add_argument('--odoo-senha', default='admin', dest='odoo_senha')
    args = parser.parse_args()
    cliente_odoo = odoo_cliente.conectar(args.odoo_url, args.odoo_db, args.odoo_usuario, args.odoo_senha)
    resultado = ingerir_arquivo(args.arquivo, args.registro, args.dsn, cliente_odoo)
    print(
        f"status={resultado.status_validacao} total_linhas={resultado.total_linhas} "
        f"total_gravado={resultado.total_gravado} eventos_orfaos={resultado.eventos_orfaos} "
        f"motivo={resultado.motivo_rejeicao}"
    )


if __name__ == '__main__':
    main()
