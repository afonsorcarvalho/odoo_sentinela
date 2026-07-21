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


def criar_driver(driver_nome, porta, baud, paridade, stopbits, endereco):
    """Instancia o driver do dispositivo. Raise ValueError se desconhecido."""
    if driver_nome == "n4aib16":
        from drivers.n4aib16 import N4AIB16
        return N4AIB16(
            port=porta, baud=baud, address=endereco,
            parity=_PARIDADE.get(paridade, "N"), stopbits=stopbits,
        )
    raise ValueError(f"driver Modbus desconhecido: {driver_nome!r}")
