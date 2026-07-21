import textwrap
from datetime import datetime, timedelta, timezone

from hub import config
from hub.leitor import Leitor

TZ = timezone(timedelta(hours=-3))

CFG = """
    hub_id: HUB-0001
    coletor_id: COL-RS485-BUS0
    firmware_version: 0.1.0
    timezone_offset: "-03:00"
    intervalo_leitura_s: 60
    caminho_chave: /tmp/coletor.pem
    caminho_dados: /tmp/dados
    mqtt: {host: localhost, port: 1883}
    barramentos:
      - porta: /dev/ttyUSB0
        baud: 9600
        paridade: N
        stop_bits: 1
        dispositivos:
          - endereco: 1
            driver: n4aib16
            canais:
              - ch: 1
                sensor_id: SNR-EXP-TEMP-01
                area_id: AREA-EXPURGO
                tipo_medida: temperatura
                unidade: C
                protocolo_origem: 4-20ma
                map: {in: [4, 20], out: [0, 100]}
"""


class _DriverFake:
    def __init__(self, valores=None, erro=False):
        self._valores = valores or [{"channel": 1, "value": 50.0, "unit": "C"}]
        self._erro = erro
    def read_channels(self, maps=None):
        if self._erro:
            raise RuntimeError("sem resposta")
        return self._valores
    def close(self):
        pass


class _BackendFake:
    def __init__(self, driver):
        self._driver = driver
        from hub.modbus_backend import MapSpec
        self.MapSpec = MapSpec
    def criar_driver(self, *a, **k):
        return self._driver


def _cfg(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(textwrap.dedent(CFG))
    return config.carregar_config(p)


def test_ler_todos_normaliza(tmp_path):
    leitor = Leitor(_cfg(tmp_path), backend=_BackendFake(_DriverFake()))
    agora = datetime(2026, 7, 21, 0, 1, tzinfo=TZ)
    leituras = leitor.ler_todos(agora)
    assert len(leituras) == 1
    r = leituras[0]
    assert r["sensor_id"] == "SNR-EXP-TEMP-01"
    assert r["valor"] == 50.0
    assert r["status_leitura"] == "ok"
    assert r["timestamp"] == agora


def test_dispositivo_offline_vira_sensor_offline(tmp_path):
    leitor = Leitor(_cfg(tmp_path), backend=_BackendFake(_DriverFake(erro=True)))
    leituras = leitor.ler_todos(datetime(2026, 7, 21, 0, 1, tzinfo=TZ))
    assert leituras[0]["status_leitura"] == "sensor_offline"
    assert leituras[0]["valor"] == 0.0
