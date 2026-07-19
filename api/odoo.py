import os
from functools import lru_cache

from ingestao import odoo_cliente

ODOO_URL = os.environ.get('ODOO_URL', 'http://localhost:8189')
ODOO_DB = os.environ.get('ODOO_DB', 'sentinela')
ODOO_USUARIO_SERVICO = os.environ.get('ODOO_USUARIO_SERVICO', 'admin')
ODOO_SENHA_SERVICO = os.environ.get('ODOO_SENHA_SERVICO', 'admin')
SITE_CODE = os.environ.get('SENTINELA_SITE_CODE', 'SITE-DEMO-01')


@lru_cache
def get_cliente_servico():
    return odoo_cliente.conectar(ODOO_URL, ODOO_DB, ODOO_USUARIO_SERVICO, ODOO_SENHA_SERVICO)
