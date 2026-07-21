import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from .auth import get_cliente_usuario_query, verificar_token_query
from .meta import obter_sensor
from .permissions import obter_sites_permitidos

router = APIRouter()

_registry: dict[str, set[asyncio.Queue]] = {}
_registry_global: set[asyncio.Queue] = set()
_sites_por_fila: dict[asyncio.Queue, frozenset] = {}


def registrar(sensor_code: str, sites_permitidos) -> asyncio.Queue:
    fila = asyncio.Queue()
    _registry.setdefault(sensor_code, set()).add(fila)
    _sites_por_fila[fila] = frozenset(sites_permitidos)
    return fila


def remover(sensor_code: str, fila: asyncio.Queue) -> None:
    filas = _registry.get(sensor_code)
    if filas is not None:
        filas.discard(fila)
        if not filas:
            _registry.pop(sensor_code, None)
    _sites_por_fila.pop(fila, None)


def registrar_global(sites_permitidos) -> asyncio.Queue:
    fila = asyncio.Queue()
    _registry_global.add(fila)
    _sites_por_fila[fila] = frozenset(sites_permitidos)
    return fila


def remover_global(fila: asyncio.Queue) -> None:
    _registry_global.discard(fila)
    _sites_por_fila.pop(fila, None)


def publicar(sensor_code: str, payload: dict) -> None:
    site_id = payload.get('site_id')
    for fila in _registry.get(sensor_code, ()):
        if site_id in _sites_por_fila.get(fila, frozenset()):
            fila.put_nowait(payload)
    for fila in _registry_global:
        if site_id in _sites_por_fila.get(fila, frozenset()):
            fila.put_nowait(payload)


@router.get('/sensores/{sensor_code}/live')
async def get_live(
    sensor_code: str,
    cliente=Depends(get_cliente_usuario_query),
    _claims=Depends(verificar_token_query),
):
    if await asyncio.to_thread(obter_sensor, cliente, sensor_code) is None:
        raise HTTPException(status_code=404, detail=f"sensor '{sensor_code}' não encontrado")

    sites_permitidos = await asyncio.to_thread(obter_sites_permitidos, cliente)
    fila = registrar(sensor_code, sites_permitidos)

    async def stream():
        try:
            while True:
                payload = await fila.get()
                yield f"data: {json.dumps(payload)}\n\n"
        finally:
            remover(sensor_code, fila)

    return StreamingResponse(stream(), media_type='text/event-stream')


@router.get('/live')
async def get_live_global(
    cliente=Depends(get_cliente_usuario_query),
    _claims=Depends(verificar_token_query),
):
    # Sem sensor_code: multiplexa eventos de TODOS os sensores PERMITIDOS pro
    # usuario numa unica conexao. Existe pra nao estourar o limite de 6
    # conexoes HTTP/1.1 persistentes por origem que os browsers aplicam --
    # com N sensores na tela (dashboard fundido), abrir 1 EventSource por
    # sensor trava os sensores alem do 6o pra sempre (achado em teste real,
    # ver docs/superpowers/plans/2026-07-19-live-sse-backend.md).
    sites_permitidos = await asyncio.to_thread(obter_sites_permitidos, cliente)
    fila = registrar_global(sites_permitidos)

    async def stream():
        try:
            while True:
                payload = await fila.get()
                yield f"data: {json.dumps(payload)}\n\n"
        finally:
            remover_global(fila)

    return StreamingResponse(stream(), media_type='text/event-stream')
