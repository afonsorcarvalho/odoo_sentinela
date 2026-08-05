"""Acervo de arquivos diários: varredura da árvore SFTP e montagem de ZIP.

Módulo puro — sem FastAPI e sem HTTP. Quem fala HTTP é arquivos_router.py.
"""
import re
from datetime import date

# Códigos do cadastro (CLI-43, SITE-DEMO-01, HUB_0001A2F3). O que este regex
# recusa é exatamente o que tornaria o caminho montado abaixo perigoso: '/',
# '.' e qualquer forma de travessia.
_RE_TOKEN = re.compile(r'^[A-Za-z0-9_-]{1,64}$')


class ParametroInvalido(ValueError):
    """Token ou data fora do formato aceito."""


def validar_token(valor: str) -> str:
    if not isinstance(valor, str) or not _RE_TOKEN.match(valor):
        raise ParametroInvalido(f'valor inválido: {valor!r}')
    return valor


def caminho_do_dia(base: str, cliente: str, site: str, data: date) -> str:
    """Caminho remoto da pasta de um dia/site, montado só com valores validados."""
    cliente = validar_token(cliente)
    site = validar_token(site)
    return f'{base}/{cliente}/{data.year:04d}/{data.month:02d}/{data.day:02d}/{site}'
