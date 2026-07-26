import os
import time
from collections import defaultdict, deque
from dataclasses import asdict

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from . import verificacao

IP_COTA = 10
IP_JANELA_S = 60
PORTAL_SECRET = os.environ.get('PORTAL_VERIFICAR_SECRET', 'dev-portal-secret-trocar')

router = APIRouter()
gestor = verificacao.Gestor()
_hits = defaultdict(deque)  # ip -> timestamps
_now = time.monotonic
_ultimo_prune = [0.0]


def reset_estado():
    global gestor
    gestor = verificacao.Gestor()
    _hits.clear()
    _ultimo_prune[0] = 0.0


def _exige_segredo(request: Request):
    if request.headers.get('x-portal-secret') != PORTAL_SECRET:
        raise HTTPException(status_code=401, detail='não autorizado')


def _ip(request: Request):
    # Endpoint autenticado (só o hop interno do Odoo chama, via _exige_segredo),
    # portanto o X-Forwarded-For é confiável: quem o define é o próprio Odoo
    # a partir do IP real do visitante do portal.
    xff = request.headers.get('x-forwarded-for', '')
    return xff.split(',')[0].strip() if xff else (request.client.host if request.client else 'desconhecido')


def _prune(now):
    if now - _ultimo_prune[0] > IP_JANELA_S:
        for ip, dq in list(_hits.items()):
            if not dq or now - dq[-1] > IP_JANELA_S:
                del _hits[ip]
        _ultimo_prune[0] = now


def _rate_ok(ip):
    agora = _now()
    _prune(agora)
    dq = _hits[ip]
    while dq and agora - dq[0] > IP_JANELA_S:
        dq.popleft()
    if len(dq) >= IP_COTA:
        return False
    dq.append(agora)
    return True


@router.post('/verificar')
async def verificar(request: Request, arquivo: UploadFile = File(...)):
    _exige_segredo(request)
    if not _rate_ok(_ip(request)):
        return JSONResponse({'erro': 'muitas requisições'}, status_code=429,
                            headers={'Retry-After': str(IP_JANELA_S)})
    dados = await arquivo.read()
    if len(dados) > verificacao.UPLOAD_MAX:
        raise HTTPException(status_code=413, detail='upload excede o limite')
    try:
        job = gestor.enfileirar(arquivo.filename, dados)
    except verificacao.FilaCheia:
        return JSONResponse({'erro': 'servidor ocupado'}, status_code=429,
                            headers={'Retry-After': '30'})
    return {'job_id': job.id, 'posicao': job.posicao}


@router.get('/verificar/{job_id}')
async def status(job_id: str, request: Request):
    _exige_segredo(request)
    job = gestor.obter(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail='job inexistente ou expirado')
    corpo = {'estado': job.estado, 'posicao': job.posicao}
    if job.estado == 'pronto':
        corpo['lote'] = asdict(job.lote)
    elif job.estado == 'erro':
        corpo['erro'] = job.erro
    return corpo
