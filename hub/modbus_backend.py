"""Isolamento do projeto modbus-connector (vendored como submodule).

Toda a dependência do vendor (manipulação de sys.path, nomes de driver)
fica confinada aqui — o resto do Hub importa daqui e mocka daqui nos testes.
"""
import os
import sys

_VENDOR = os.path.join(os.path.dirname(__file__), "vendor", "modbus-connector")
if _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)

from common.scaling import MapSpec  # noqa: E402  (re-export)

_PARIDADE = {"N": "N", "E": "E", "O": "O"}


class _AdaptadorDriver:
    """Interface uniforme que o leitor consome: ler(maps) + close().

    Confina no seam do vendor a diferença de nome de método e de forma das
    entries entre famílias de driver.
    """
    def __init__(self, driver):
        self._driver = driver

    def close(self):
        self._driver.close()


class AdaptadorN4(_AdaptadorDriver):
    """N4AIB16: read_channels já devolve entries com 'channel'."""
    def ler(self, maps=None):
        return self._driver.read_channels(maps=maps)


class AdaptadorRS(_AdaptadorDriver):
    """RS-WS-N01-2D: read_measurements devolve 'name'/'register'; injeta channel."""
    def ler(self, maps=None):
        entries = self._driver.read_measurements(maps=maps)
        for i, entry in enumerate(entries):
            entry["channel"] = i + 1
        return entries


def criar_driver(driver_nome, porta, baud, paridade, stopbits, endereco):
    """Instancia o adapter do dispositivo. Raise ValueError se desconhecido."""
    if driver_nome == "n4aib16":
        from drivers.n4aib16 import N4AIB16
        return AdaptadorN4(N4AIB16(
            port=porta, baud=baud, address=endereco,
            parity=_PARIDADE.get(paridade, "N"), stopbits=stopbits,
        ))
    if driver_nome == "rs_ws_n01_2d":
        from drivers.rs_ws_n01_2d import RSWSN012D
        return AdaptadorRS(RSWSN012D(
            port=porta, baud=baud, address=endereco,
            parity=_PARIDADE.get(paridade, "N"), stopbits=stopbits,
        ))
    raise ValueError(f"driver Modbus desconhecido: {driver_nome!r}")
