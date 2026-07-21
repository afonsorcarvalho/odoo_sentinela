"""Entrypoint chamado pelo Event Manager do SFTPGo após um upload.

Uso: python -m ingestao.receber_upload <caminho_do_arquivo>
Config via ambiente: SENTINELA_REGISTRO, SENTINELA_DSN, SENTINELA_ODOO_URL,
SENTINELA_ODOO_DB, SENTINELA_ODOO_USER, SENTINELA_ODOO_SENHA.
"""
import os
import sys

from . import ingestor, odoo_cliente


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    caminho = argv[0]
    registro = os.environ.get("SENTINELA_REGISTRO", "ingestao/coletores_conhecidos.json")
    dsn = os.environ.get("SENTINELA_DSN", "postgresql://sentinela:sentinela@localhost:5433/sentinela")
    cliente = odoo_cliente.conectar(
        os.environ.get("SENTINELA_ODOO_URL", "http://localhost:8189"),
        os.environ.get("SENTINELA_ODOO_DB", "sentinela"),
        os.environ.get("SENTINELA_ODOO_USER", "admin"),
        os.environ.get("SENTINELA_ODOO_SENHA", "admin"),
    )
    resultado = ingestor.ingerir_arquivo(caminho, registro, dsn, cliente)
    print(f"status={resultado.status_validacao} gravado={resultado.total_gravado} "
          f"motivo={resultado.motivo_rejeicao}")
    return resultado


if __name__ == "__main__":
    main()
