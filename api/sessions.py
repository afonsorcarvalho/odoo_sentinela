import threading
import time

_lock = threading.Lock()
_sessions = {}


def guardar(jti, cliente, exp):
    with _lock:
        _sessions[jti] = (cliente, exp)


def obter(jti):
    with _lock:
        entrada = _sessions.get(jti)
        if entrada is None:
            return None
        cliente, exp = entrada
        if exp < time.time():
            del _sessions[jti]
            return None
        return cliente


def remover(jti):
    with _lock:
        _sessions.pop(jti, None)
