"""Verificação de upload: descompacta zip (com guards) e roda o verificador.
Camada sync; a fila/worker vem no proximo stage.
"""
import io
import zipfile

from ingestao import verificador

from .verificacao_chaves import chaves_do_odoo

UPLOAD_MAX = 25 * 1024 * 1024
DESCOMPRIMIDO_MAX = 200 * 1024 * 1024
ARQUIVOS_MAX = 500


class LimiteExcedido(Exception):
    pass


def coletar(nome_upload, dados):
    if not nome_upload.lower().endswith('.zip'):
        return [(nome_upload, dados)]
    itens = []
    total = 0
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        infos = [i for i in z.infolist() if not i.is_dir()
                 and not i.filename.lower().endswith('.zip')]  # ignora aninhado
        if len(infos) > ARQUIVOS_MAX:
            raise LimiteExcedido(f'zip com mais de {ARQUIVOS_MAX} arquivos')
        for info in infos:
            total += info.file_size
            if total > DESCOMPRIMIDO_MAX:
                raise LimiteExcedido('conteúdo descomprimido excede o limite')
            itens.append((info.filename, z.read(info)))
    return itens


def verificar_upload(nome_upload, dados, chaves_pem=None):
    itens = coletar(nome_upload, dados)
    return verificador.verificar_itens(itens, chaves_pem=chaves_pem or chaves_do_odoo())
