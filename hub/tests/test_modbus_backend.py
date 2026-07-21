import pytest

from hub import modbus_backend


def test_map_spec_reexportado_aplica_escala():
    spec = modbus_backend.MapSpec(channels={1}, in_min=4, in_max=20, out_min=0, out_max=100)
    assert spec.apply(4) == 0
    assert spec.apply(20) == 100
    assert spec.apply(12) == 50


def test_criar_driver_desconhecido_falha():
    with pytest.raises(ValueError):
        modbus_backend.criar_driver("inexistente", "/dev/null", 9600, "N", 1, 1)
