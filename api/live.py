import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from .auth import verificar_token_query
from .meta import obter_sensor
from .odoo import get_cliente_servico

router = APIRouter()

_registry: dict[str, set[asyncio.Queue]] = {}


def registrar(sensor_code: str) -> asyncio.Queue:
    fila = asyncio.Queue()
    _registry.setdefault(sensor_code, set()).add(fila)
    return fila


def remover(sensor_code: str, fila: asyncio.Queue) -> None:
    filas = _registry.get(sensor_code)
    if filas is None:
        return
    filas.discard(fila)
    if not filas:
        _registry.pop(sensor_code, None)


def publicar(sensor_code: str, payload: dict) -> None:
    for fila in _registry.get(sensor_code, ()):
        fila.put_nowait(payload)


@router.get('/sensores/{sensor_code}/live')
async def get_live(
    sensor_code: str,
    cliente=Depends(get_cliente_servico),
    _claims=Depends(verificar_token_query),
):
    if await asyncio.to_thread(obter_sensor, cliente, sensor_code) is None:
        raise HTTPException(status_code=404, detail=f"sensor '{sensor_code}' não encontrado")

    fila = registrar(sensor_code)

    async def stream():
        try:
            while True:
                payload = await fila.get()
                yield f"data: {json.dumps(payload)}\n\n"
        finally:
            remover(sensor_code, fila)

    return StreamingResponse(stream(), media_type='text/event-stream')
