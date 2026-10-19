"""Rota interna que devolve o ZIP do dia de um cliente/site do acervo SFTP.

Fala HTTP; a lógica pura de varredura/zip mora em arquivos.py. Rota interna:
só o Odoo chama, com o mesmo segredo do publicar-config.
"""
import hmac
import os
import tempfile
from datetime import date

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .arquivos import ParametroInvalido, caminho_do_dia, listar_arquivos_do_dia, montar_zip
from .config_publisher import _sftp_conectar

router = APIRouter()

_SECRET = os.environ.get('CONFIG_PUBLISH_SECRET', '')
# Defaults no código de propósito: o docker-compose de produção não muda.
SFTP_UPLOADS = os.environ.get('SFTP_UPLOADS', '/uploads')
_MAX_BYTES_PADRAO = 500 * 1024 * 1024


def _ler_max_bytes():
    # int(os.environ[...]) direto na import time derrubava TODA a api (live,
    # historico, config-publish) se ARQUIVOS_ZIP_MAX_BYTES viesse malformado
    # no .env — um typo numa rota vira downtime total. Fallback pro default
    # em vez de deixar o ValueError propagar do import de api.main.
    bruto = os.environ.get('ARQUIVOS_ZIP_MAX_BYTES')
    if bruto is None:
        return _MAX_BYTES_PADRAO
    try:
        return int(bruto)
    except ValueError:
        return _MAX_BYTES_PADRAO


# Nome de módulo continua MAX_BYTES de propósito: os testes existentes fazem
# monkeypatch.setattr(arquivos_router, 'MAX_BYTES', ...) direto nesse nome.
MAX_BYTES = _ler_max_bytes()


def _remover(caminho):
    def _limpar():
        try:
            os.unlink(caminho)
        except OSError:
            pass
    return _limpar


@router.get('/internal/arquivos/zip')
def zip_do_dia(cliente: str, site: str, data: str, x_config_secret: str = Header(default='')):
    """ZIP com todos os arquivos de um dia/site do acervo.

    Rota interna: só o Odoo chama, com o mesmo segredo do publicar-config.
    Nenhum fragmento de caminho vem do chamador — cliente/site/data são
    validados e o caminho é montado aqui.
    """
    if not _SECRET or not hmac.compare_digest(x_config_secret, _SECRET):
        raise HTTPException(status_code=401, detail='secret inválido')
    try:
        dia = date.fromisoformat(data)
        raiz = caminho_do_dia(SFTP_UPLOADS, cliente, site, dia)
    except (ValueError, ParametroInvalido) as e:
        raise HTTPException(status_code=400, detail=str(e))

    transport, sftp = _sftp_conectar()
    try:
        encontrados = listar_arquivos_do_dia(sftp, raiz)
        if not encontrados:
            raise HTTPException(status_code=404, detail='nenhum arquivo para este dia/site')
        total = sum(tamanho for _rel, tamanho in encontrados)
        if total > MAX_BYTES:
            raise HTTPException(status_code=413, detail=f'{total} bytes acima do teto {MAX_BYTES}')
        tmp = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
        tmp.close()
        try:
            montar_zip(sftp, raiz, encontrados, tmp.name)
        except Exception:
            # montar_zip pode ter escrito um ZIP parcial antes de estourar
            # (ex.: SFTP caiu no meio de um arquivo). O tempfile é nosso —
            # ninguém mais vai limpar esse rastro se não limparmos aqui.
            _remover(tmp.name)()
            raise
    finally:
        # Se sftp.close()/transport.close() estourasse sem essa proteção, a
        # exceção do close() mascararia o retorno normal — e, se montar_zip
        # já tivesse terminado, o tempfile ficaria órfão (o FileResponse com
        # o BackgroundTask de limpeza nunca chegaria a ser construído).
        for fechar in (sftp.close, transport.close):
            try:
                fechar()
            except Exception:
                pass

    return FileResponse(
        tmp.name,
        media_type='application/zip',
        filename=f'sentinela_{site}_{data}.zip',
        background=BackgroundTask(_remover(tmp.name)),
    )
