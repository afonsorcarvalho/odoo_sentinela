"""Adapters de driver: interface uniforme ler(maps)/close sobre o vendor."""
import pytest

from hub import modbus_backend
from hub.modbus_backend import AdaptadorN4, AdaptadorRS


def test_map_spec_reexportado_aplica_escala():
    spec = modbus_backend.MapSpec(channels={1}, in_min=4, in_max=20, out_min=0, out_max=100)
    assert spec.apply(4) == 0
    assert spec.apply(20) == 100
    assert spec.apply(12) == 50


def test_criar_driver_desconhecido_falha():
    with pytest.raises(ValueError):
        modbus_backend.criar_driver("inexistente", "/dev/null", 9600, "N", 1, 1)


class _VendorN4Fake:
    """Simula N4AIB16.read_channels: entries já têm 'channel'."""
    def __init__(self):
        self.fechado = False
        self.maps_recebido = "NAO_CHAMADO"
    def read_channels(self, maps=None):
        self.maps_recebido = maps
        return [{"channel": 1, "value": 12.5, "unit": "mA", "register": 0}]
    def close(self):
        self.fechado = True


class _VendorRSFake:
    """Simula RSWSN012D.read_measurements: entries têm 'name'/'register', SEM 'channel'."""
    def __init__(self):
        self.fechado = False
        self.maps_recebido = "NAO_CHAMADO"
    def read_measurements(self, maps=None):
        self.maps_recebido = maps
        return [
            {"name": "humidity", "register": 0, "value": 50.8, "unit": "%RH"},
            {"name": "temperature", "register": 1, "value": 25.9, "unit": "C"},
        ]
    def close(self):
        self.fechado = True


def test_adaptador_n4_repassa_entries_e_maps():
    vendor = _VendorN4Fake()
    ad = AdaptadorN4(vendor)
    entries = ad.ler(maps=["SPEC"])
    assert vendor.maps_recebido == ["SPEC"]           # maps repassado
    assert entries[0]["channel"] == 1                 # channel intacto
    assert entries[0]["value"] == 12.5


def test_adaptador_rs_injeta_channel_1based():
    vendor = _VendorRSFake()
    ad = AdaptadorRS(vendor)
    entries = ad.ler(maps=None)
    assert [e["channel"] for e in entries] == [1, 2]  # 1=umidade, 2=temp
    assert entries[0]["value"] == 50.8 and entries[0]["unit"] == "%RH"
    assert entries[1]["value"] == 25.9 and entries[1]["unit"] == "C"


def test_adaptadores_delegam_close():
    v1, v2 = _VendorN4Fake(), _VendorRSFake()
    AdaptadorN4(v1).close()
    AdaptadorRS(v2).close()
    assert v1.fechado and v2.fechado


def test_criar_driver_despacha_rs(monkeypatch):
    import hub.modbus_backend as mb

    class _RSFake:
        def __init__(self, **kw): self.kw = kw
    # patch no ponto de import lazy: injeta um módulo drivers.rs_ws_n01_2d falso
    import sys, types
    mod = types.ModuleType("drivers.rs_ws_n01_2d")
    mod.RSWSN012D = _RSFake
    monkeypatch.setitem(sys.modules, "drivers.rs_ws_n01_2d", mod)
    ad = mb.criar_driver("rs_ws_n01_2d", "/dev/ttyUSB1", 9600, "N", 1, 2)
    assert isinstance(ad, mb.AdaptadorRS)
    assert ad._driver.kw["address"] == 2 and ad._driver.kw["baud"] == 9600


def test_criar_driver_despacha_n4(monkeypatch):
    import hub.modbus_backend as mb, sys, types
    class _N4Fake:
        def __init__(self, **kw): self.kw = kw
    mod = types.ModuleType("drivers.n4aib16")
    mod.N4AIB16 = _N4Fake
    monkeypatch.setitem(sys.modules, "drivers.n4aib16", mod)
    ad = mb.criar_driver("n4aib16", "/dev/ttyUSB0", 9600, "N", 1, 1)
    assert isinstance(ad, mb.AdaptadorN4)


def test_criar_driver_desconhecido_levanta():
    import hub.modbus_backend as mb
    import pytest
    with pytest.raises(ValueError):
        mb.criar_driver("driver_inexistente", "/dev/x", 9600, "N", 1, 1)


class _VendorGenericoFake:
    """Simula Generico.read_measurements: entries já têm 'channel'."""
    def __init__(self):
        self.fechado = False
        self.maps_recebido = "NAO_CHAMADO"
    def read_measurements(self, maps=None):
        self.maps_recebido = maps
        return [{"channel": 1, "value": 5.1, "unit": "%RH"}]
    def close(self):
        self.fechado = True


def test_adaptador_generico_repassa_entries_e_maps():
    from hub.modbus_backend import AdaptadorGenerico
    vendor = _VendorGenericoFake()
    ad = AdaptadorGenerico(vendor)
    entries = ad.ler(maps=["SPEC"])
    assert vendor.maps_recebido == ["SPEC"]
    assert entries[0]["channel"] == 1
    assert entries[0]["value"] == 5.1


def test_criar_driver_despacha_generico(monkeypatch):
    import hub.modbus_backend as mb, sys, types

    class _GenericoFake:
        def __init__(self, **kw): self.kw = kw

    mod = types.ModuleType("drivers.generico")
    mod.Generico = _GenericoFake
    monkeypatch.setitem(sys.modules, "drivers.generico", mod)
    registros = [{"ch": 1, "address": 1, "function": 3, "data_type": "int16",
                  "scale": 0.1, "offset": 0.0, "count": 1}]
    ad = mb.criar_driver("generico", "/dev/ttyUSB2", 9600, "N", 1, 3, registros=registros)
    assert isinstance(ad, mb.AdaptadorGenerico)
    assert ad._driver.kw["address"] == 3 and ad._driver.kw["baud"] == 9600
    assert ad._driver.kw["registros"] == registros
