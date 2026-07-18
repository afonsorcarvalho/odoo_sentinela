import asyncio

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
