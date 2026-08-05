"""Acervo de arquivos diários: varredura da árvore SFTP e montagem de ZIP.

Módulo puro — sem FastAPI e sem HTTP. Quem fala HTTP é arquivos_router.py.
"""
import re
import stat
from datetime import date

# Códigos do cadastro (CLI-43, SITE-DEMO-01, HUB_0001A2F3). O que este regex
# recusa é exatamente o que tornaria o caminho montado abaixo perigoso: '/',
# '.' e qualquer forma de travessia.
_RE_TOKEN = re.compile(r'^[A-Za-z0-9_-]{1,64}$')


class ParametroInvalido(ValueError):
    """Token ou data fora do formato aceito."""


def validar_token(valor: str) -> str:
    if not isinstance(valor, str) or not _RE_TOKEN.fullmatch(valor):
        raise ParametroInvalido(f'valor inválido: {valor!r}')
    return valor


def caminho_do_dia(base: str, cliente: str, site: str, data: date) -> str:
    """Caminho remoto da pasta de um dia/site, montado só com valores validados."""
    cliente = validar_token(cliente)
    site = validar_token(site)
    return f'{base}/{cliente}/{data.year:04d}/{data.month:02d}/{data.day:02d}/{site}'


def listar_arquivos_do_dia(sftp, raiz: str, profundidade_max: int = 3):
    """Arquivos regulares sob `raiz`, como (caminho_relativo, tamanho).

    `profundidade_max=3` é a convenção do acervo: HUB/COLETOR/arquivo.txt.
    Só entra o que for arquivo regular — symlink e diretório fundo demais
    ficam de fora. Pasta inexistente devolve lista vazia (o chamador traduz
    em 404), não exceção.
    """
    encontrados = []

    def varrer(caminho_abs, prefixo, profundidade):
        try:
            entradas = sftp.listdir_attr(caminho_abs)
        except IOError:
            return
        for attr in entradas:
            rel = f'{prefixo}{attr.filename}'
            if stat.S_ISREG(attr.st_mode):
                encontrados.append((rel, attr.st_size))
            elif stat.S_ISDIR(attr.st_mode) and profundidade < profundidade_max:
                varrer(f'{caminho_abs}/{attr.filename}', f'{rel}/', profundidade + 1)

    varrer(raiz.rstrip('/'), '', 1)
    return sorted(encontrados)
