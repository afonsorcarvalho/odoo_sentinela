"""Garante que o driver RS-WS-N01-2D está presente no submódulo (bump fc70ffb)."""
from hub import modbus_backend  # noqa: F401  (garante sys.path do vendor)


def test_rs_ws_n01_2d_importavel():
    from drivers.rs_ws_n01_2d import RSWSN012D
    # read_measurements é a interface que o AdaptadorRS vai consumir (Task 3).
    assert hasattr(RSWSN012D, "read_measurements")


def test_n4aib16_continua_importavel():
    from drivers.n4aib16 import N4AIB16
    assert hasattr(N4AIB16, "read_channels")
