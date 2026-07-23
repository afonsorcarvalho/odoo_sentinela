import argparse
from dataclasses import dataclass
from datetime import datetime

from . import odoo_cliente, timescale, validador


@dataclass
class ResultadoIngestao:
    status_validacao: str
    motivo_rejeicao: str
    total_linhas: int
    total_gravado: int
    eventos_orfaos: int = 0


def _processar_leituras(dsn, info_coletor, rv, pubkey_fp, ts_ingestao):
    conn = timescale.conectar(dsn)
    try:
        return timescale.inserir_leituras(
            conn, info_coletor['site_code'], rv.coletor_id, rv.leituras,
            cliente_id=rv.cliente_id, pubkey_fingerprint=pubkey_fp,
            file_hash=rv.hash_final, ts_ingestao=ts_ingestao)
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

    status_validacao = resultado_validacao.status_validacao
    motivo_rejeicao = resultado_validacao.motivo_rejeicao
    total_gravado = 0
    eventos_orfaos = 0
    if status_validacao in ('valido', 'incompleto'):
        # F: o tenant do header tem que casar com o cadastro do coletor. Só faz sentido
        # checar depois que o crypto-gate passou (senão um cliente_id de header adulterado
        # mascara o motivo real de rejeição, que é a assinatura inválida).
        # NOTA (I3): trocar o `ref` do partner no Odoo depois de arquivos publicados invalida
        # em cadeia todos os arquivos em trânsito desse tenant — o header carrega o `ref`
        # congelado no momento da publicação, e a ingestão recalcula a partir do cadastro
        # atual. Isso é fail-closed por desenho; operadores devem republicar os arquivos ou
        # evitar alterar `ref` de tenants com coletores ativos.
        if (resultado_validacao.site_id != info_coletor['site_code']
                or resultado_validacao.cliente_id != info_coletor['cliente_id']):
            status_validacao = 'invalido'
            motivo_rejeicao = (f"tenant do header diverge do cadastro: header="
                               f"({resultado_validacao.cliente_id}/{resultado_validacao.site_id}) "
                               f"cadastro=({info_coletor['cliente_id']}/{info_coletor['site_code']})")
        elif resultado_validacao.tipo_arquivo == 'alarmes':
            try:
                eventos_orfaos = _processar_alarmes(cliente_odoo, info_coletor, resultado_validacao)
                total_gravado = len(resultado_validacao.eventos)
            except ValueError as exc:
                status_validacao = 'invalido'
                motivo_rejeicao = str(exc)
                total_gravado = 0
        else:
            total_gravado = _processar_leituras(
                dsn, info_coletor, resultado_validacao,
                resultado_validacao.pubkey_fingerprint, datetime.utcnow())

    odoo_cliente.escrever_ledger(
        cliente_odoo, info_coletor['id'], resultado_validacao.tipo_arquivo, resultado_validacao.data_referencia,
        status_validacao, motivo_rejeicao,
        resultado_validacao.total_linhas, resultado_validacao.hash_final, resultado_validacao.assinatura,
    )

    return ResultadoIngestao(
        status_validacao=status_validacao,
        motivo_rejeicao=motivo_rejeicao,
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
