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


class _BackendMulti:
    """Backend fake que despacha driver por endereço do dispositivo."""
    def __init__(self, por_endereco):
        self._por_endereco = por_endereco  # dict[int, driver]
        from hub.modbus_backend import MapSpec
        self.MapSpec = MapSpec
    def criar_driver(self, driver_nome, porta, baud, paridade, stopbits, endereco):
        return self._por_endereco[endereco]


class _BackendConstrucaoFalha:
    """criar_driver devolve driver bom no endereço 1 e estoura no 2."""
    def __init__(self, driver_bom):
        self._bom = driver_bom
        from hub.modbus_backend import MapSpec
        self.MapSpec = MapSpec
    def criar_driver(self, driver_nome, porta, baud, paridade, stopbits, endereco):
        if endereco == 2:
            raise ValueError(f"driver Modbus desconhecido: {driver_nome!r}")
        return self._bom


class _DriverExplode:
    """Driver que estoura com uma exceção arbitrária (não RuntimeError)."""
    def __init__(self, exc):
        self._exc = exc
    def read_channels(self, maps=None):
        raise self._exc
    def close(self):
        pass


def _cfg(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(textwrap.dedent(CFG))
    return config.carregar_config(p)


CFG_2DISP = """
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
                sensor_id: SNR-BOM
                area_id: AREA-EXPURGO
                tipo_medida: temperatura
                unidade: C
                protocolo_origem: 4-20ma
                map: {in: [4, 20], out: [0, 100]}
          - endereco: 2
            driver: n4aib16
            canais:
              - ch: 1
                sensor_id: SNR-RUIM
                area_id: AREA-EXPURGO
                tipo_medida: temperatura
                unidade: C
                protocolo_origem: 4-20ma
                map: {in: [4, 20], out: [0, 100]}
"""


def _cfg2(tmp_path):
    p = tmp_path / "c2.yaml"
    p.write_text(textwrap.dedent(CFG_2DISP))
    return config.carregar_config(p)


CFG_2CANAIS = """
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
                sensor_id: SNR-1
                area_id: AREA-EXPURGO
                tipo_medida: temperatura
                unidade: C
                protocolo_origem: 4-20ma
                map: {in: [4, 20], out: [0, 100]}
              - ch: 2
                sensor_id: SNR-2
                area_id: AREA-EXPURGO
                tipo_medida: temperatura
                unidade: C
                protocolo_origem: 4-20ma
                map: {in: [4, 20], out: [0, 100]}
"""


def _cfg_2canais(tmp_path):
    p = tmp_path / "c3.yaml"
    p.write_text(textwrap.dedent(CFG_2CANAIS))
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


def test_normalizar_aplica_calibracao_e_carimba_coeficientes():
    from hub.config import CanalConfig
    from hub.leitor import Leitor
    canal = CanalConfig(
        ch=1, sensor_id='SNR-1', area_id='EXPURGO', tipo_medida='temperatura',
        unidade='C', protocolo_origem='4-20ma', map_in=(4, 20), map_out=(0, 150),
        calibracao={'cert_ver': 3, 'ganho': 0.965, 'offset': 0.33})
    # nominal (já mapeado pelo backend) = 100.0 → corrigido = 0.965*100 + 0.33 = 96.83
    leitura = Leitor._normalizar(object.__new__(Leitor), canal, 100.0, 'ok', 'AGORA')
    assert leitura['cert_ver'] == 3
    assert leitura['cal_ganho'] == 0.965
    assert leitura['cal_offset'] == 0.33
    assert abs(leitura['valor'] - 96.83) < 1e-9


def test_indexerror_num_dispositivo_nao_derruba_os_outros(tmp_path):
    bom = _DriverFake([{"channel": 1, "value": 42.0, "unit": "C"}])
    ruim = _DriverExplode(IndexError("list index out of range"))
    backend = _BackendMulti({1: bom, 2: ruim})
    leitor = Leitor(_cfg2(tmp_path), backend=backend)
    leituras = leitor.ler_todos(datetime(2026, 7, 24, 0, 1, tzinfo=TZ))
    por_sensor = {r["sensor_id"]: r for r in leituras}
    assert por_sensor["SNR-BOM"]["status_leitura"] == "ok"
    assert por_sensor["SNR-BOM"]["valor"] == 42.0
    assert por_sensor["SNR-RUIM"]["status_leitura"] == "sensor_offline"
    assert por_sensor["SNR-RUIM"]["valor"] == 0.0


def test_falha_em_canal_do_meio_nao_deixa_leitura_ok_duplicada(tmp_path):
    """Dispositivo com 2 canais: ch1 lê ok, ch2 estoura (TypeError em float(None)).

    Antes do fix, ch1 já tinha sido `leituras.append(...ok...)` dentro do try
    quando ch2 lança — e o `except` reprocessava TODOS os canais do
    dispositivo como sensor_offline, gerando 2 entradas para SNR-1 (uma ok,
    uma sensor_offline) além da entrada sensor_offline de SNR-2. O contrato é
    uma leitura por sensor_id por varredura.
    """
    driver = _DriverFake([
        {"channel": 1, "value": 50.0, "unit": "C"},
        {"channel": 2, "value": None, "unit": "C"},
    ])
    backend = _BackendFake(driver)
    leitor = Leitor(_cfg_2canais(tmp_path), backend=backend)
    leituras = leitor.ler_todos(datetime(2026, 7, 24, 0, 1, tzinfo=TZ))

    sensor_ids = [r["sensor_id"] for r in leituras]
    assert sorted(sensor_ids) == ["SNR-1", "SNR-2"]
    assert len(leituras) == 2  # uma leitura por sensor_id, sem duplicata

    por_sensor = {r["sensor_id"]: r for r in leituras}
    assert por_sensor["SNR-1"]["status_leitura"] == "sensor_offline"
    assert por_sensor["SNR-1"]["valor"] == 0.0
    assert por_sensor["SNR-2"]["status_leitura"] == "sensor_offline"
    assert por_sensor["SNR-2"]["valor"] == 0.0


def test_dispositivo_que_nao_instancia_nao_derruba_boot(tmp_path):
    bom = _DriverFake([{"channel": 1, "value": 42.0, "unit": "C"}])
    backend = _BackendConstrucaoFalha(bom)
    # NÃO deve levantar:
    leitor = Leitor(_cfg2(tmp_path), backend=backend)
    leituras = leitor.ler_todos(datetime(2026, 7, 24, 0, 1, tzinfo=TZ))
    por_sensor = {r["sensor_id"]: r for r in leituras}
    # dispositivo bom publica normal
    assert por_sensor["SNR-BOM"]["status_leitura"] == "ok"
    assert por_sensor["SNR-BOM"]["valor"] == 42.0
    # dispositivo que não instanciou vira sensor_offline (visível no dashboard)
    assert por_sensor["SNR-RUIM"]["status_leitura"] == "sensor_offline"
    assert por_sensor["SNR-RUIM"]["valor"] == 0.0
