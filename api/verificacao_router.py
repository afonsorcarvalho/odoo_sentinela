import time
from collections import defaultdict, deque
from dataclasses import asdict

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from . import verificacao

IP_COTA = 10
IP_JANELA_S = 60

router = APIRouter()
gestor = verificacao.Gestor()
_hits = defaultdict(deque)  # ip -> timestamps


def reset_estado():
    global gestor
    gestor = verificacao.Gestor()
    _hits.clear()


def _ip(request: Request):
    xff = request.headers.get('x-forwarded-for', '')
    return xff.split(',')[0].strip() if xff else (request.client.host if request.client else 'desconhecido')


def _rate_ok(ip):
    agora = time.monotonic()
    dq = _hits[ip]
    while dq and agora - dq[0] > IP_JANELA_S:
        dq.popleft()
    if len(dq) >= IP_COTA:
        return False
    dq.append(agora)
    return True


@router.post('/verificar')
async def verificar(request: Request, arquivo: UploadFile = File(...)):
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
async def status(job_id: str):
    job = gestor.obter(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail='job inexistente ou expirado')
    corpo = {'estado': job.estado, 'posicao': job.posicao}
    if job.estado == 'pronto':
        corpo['lote'] = asdict(job.lote)
    elif job.estado == 'erro':
        corpo['erro'] = job.erro
    return corpo
