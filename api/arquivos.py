"""Acervo de arquivos diários: varredura da árvore SFTP e montagem de ZIP.

Módulo puro — sem FastAPI e sem HTTP. Quem fala HTTP é arquivos_router.py.
"""
import re
import shutil
import stat
import zipfile
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
    ficam de fora. Pasta do dia inexistente devolve lista vazia (o chamador
    traduz em 404), não exceção.

    Só a pasta do dia é tolerante a IOError. Uma falha de SFTP no meio da
    árvore (ex.: listdir_attr de um HUB/COLETOR específico) PROPAGA: engolir
    aqui faria o ZIP sair completo em aparência e incompleto de fato — uma
    mentira silenciosa que nada no resto do caminho detecta.
    """
    encontrados = []

    # `varrer` nunca captura IOError — um try/except em volta da chamada de
    # topo pegaria também as falhas de qualquer nível de recursão, porque é
    # assim que a pilha de exceções do Python se desenrola. Por isso só a
    # listagem da RAIZ (fora deste helper) é protegida; a recursão em si é
    # sempre "deixa estourar".
    def varrer(entradas, caminho_abs, prefixo, profundidade):
        for attr in entradas:
            nome = attr.filename
            if nome in ('.', '..'):
                continue
            rel = f'{prefixo}{nome}'
            if stat.S_ISREG(attr.st_mode):
                encontrados.append((rel, attr.st_size))
            elif stat.S_ISDIR(attr.st_mode) and profundidade < profundidade_max:
                caminho_filho = f'{caminho_abs}/{nome}'
                # falhas aqui propagam para fora de listar_arquivos_do_dia
                varrer(sftp.listdir_attr(caminho_filho), caminho_filho, f'{rel}/', profundidade + 1)

    raiz = raiz.rstrip('/')
    try:
        entradas_raiz = sftp.listdir_attr(raiz)
    except IOError:
        return []  # só a pasta do dia ausente vira lista vazia -> 404
    varrer(entradas_raiz, raiz, '', 1)
    return sorted(encontrados)


_BLOCO = 1024 * 1024


def montar_zip(sftp, raiz: str, arquivos, destino: str) -> None:
    """Escreve em `destino` um ZIP com os arquivos, preservando HUB/COLETOR/.

    Cópia byte-a-byte via copyfileobj em modo binário: nada de ler como texto,
    nada de decodificar. O rodapé assinado tem que sobreviver intacto.
    """
    raiz = raiz.rstrip('/')
    with zipfile.ZipFile(destino, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for rel, _tamanho in arquivos:
            origem = sftp.open(f'{raiz}/{rel}', 'rb')
            try:
                # prefetch multiplica a taxa de leitura do paramiko; o duplo
                # de teste não tem o método, daí o hasattr.
                if hasattr(origem, 'prefetch'):
                    origem.prefetch()
                with zf.open(rel, 'w') as destino_membro:
                    shutil.copyfileobj(origem, destino_membro, _BLOCO)
            finally:
                origem.close()
