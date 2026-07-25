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
    def ler(self, maps=None):
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
    def criar_driver(self, *a, registros=None, **k):
        return self._driver


class _BackendRegistrosFake:
    """Backend fake que grava o `registros` recebido em criar_driver."""
    def __init__(self, driver):
        self._driver = driver
        self.registros_recebido = "NAO_CHAMADO"
        from hub.modbus_backend import MapSpec
        self.MapSpec = MapSpec
    def criar_driver(self, driver_nome, porta, baud, paridade, stopbits, endereco, registros=None):
        self.registros_recebido = registros
        return self._driver


class _BackendMulti:
    """Backend fake que despacha driver por endereço do dispositivo."""
    def __init__(self, por_endereco):
        self._por_endereco = por_endereco  # dict[int, driver]
        from hub.modbus_backend import MapSpec
        self.MapSpec = MapSpec
    def criar_driver(self, driver_nome, porta, baud, paridade, stopbits, endereco, registros=None):
        return self._por_endereco[endereco]


class _BackendConstrucaoFalha:
    """criar_driver devolve driver bom no endereço 1 e estoura no 2."""
    def __init__(self, driver_bom):
        self._bom = driver_bom
        from hub.modbus_backend import MapSpec
        self.MapSpec = MapSpec
    def criar_driver(self, driver_nome, porta, baud, paridade, stopbits, endereco, registros=None):
        if endereco == 2:
            raise ValueError(f"driver Modbus desconhecido: {driver_nome!r}")
        return self._bom


class _DriverExplode:
    """Driver que estoura com uma exceção arbitrária (não RuntimeError)."""
    def __init__(self, exc):
        self._exc = exc
    def ler(self, maps=None):
        raise self._exc
    def close(self):
        pass


def _cfg(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(textwrap.dedent(CFG))
    return config.carregar_config(p)


CFG_SEM_MAP = """
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
              - ch: 2
                sensor_id: SNR-RS-NATIVO
                area_id: AREA-EXPURGO
                tipo_medida: temperatura
                unidade: C
                protocolo_origem: modbus
"""


def _cfg_sem_map(tmp_path):
    p = tmp_path / "c_sem_map.yaml"
    p.write_text(textwrap.dedent(CFG_SEM_MAP))
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


class _DriverFalhaDepoisRecupera:
    """Falha nas N primeiras chamadas, depois passa a responder ok."""
    def __init__(self, n_falhas, valores=None):
        self._n_falhas = n_falhas
        self._chamadas = 0
        self._valores = valores or [{"channel": 1, "value": 50.0, "unit": "C"}]
    def ler(self, maps=None):
        self._chamadas += 1
        if self._chamadas <= self._n_falhas:
            raise RuntimeError("sem resposta")
        return self._valores
    def close(self):
        pass


def test_log_de_falha_dedupe_e_recuperacao(tmp_path, capsys):
    """Falha nos ciclos 1 e 2 loga UMA vez só; recuperação no ciclo 3 loga a recuperação."""
    driver = _DriverFalhaDepoisRecupera(n_falhas=2)
    leitor = Leitor(_cfg(tmp_path), backend=_BackendFake(driver))
    agora = datetime(2026, 7, 24, 0, 1, tzinfo=TZ)

    leitor.ler_todos(agora)
    leitor.ler_todos(agora)
    saida_falhas = capsys.readouterr().out
    linhas_falha = [l for l in saida_falhas.splitlines() if "leitura falhou" in l]
    assert len(linhas_falha) == 1
    assert "driver=n4aib16" in linhas_falha[0]
    assert "porta=/dev/ttyUSB0" in linhas_falha[0]
    assert "endereco=1" in linhas_falha[0]
    assert "sensor=SNR-EXP-TEMP-01" in linhas_falha[0]

    leitor.ler_todos(agora)
    saida_recuperacao = capsys.readouterr().out
    linhas_recuperacao = [l for l in saida_recuperacao.splitlines() if "leitura recuperada" in l]
    assert len(linhas_recuperacao) == 1
    assert "driver=n4aib16" in linhas_recuperacao[0]
    assert "porta=/dev/ttyUSB0" in linhas_recuperacao[0]
    assert "endereco=1" in linhas_recuperacao[0]
    assert "sensor=SNR-EXP-TEMP-01" in linhas_recuperacao[0]

    # mais um ciclo ok: não deve repetir a recuperação
    leitor.ler_todos(agora)
    saida_extra = capsys.readouterr().out
    assert "leitura recuperada" not in saida_extra


def test_canal_sem_map_preserva_valor_nativo(tmp_path):
    from hub.config import CanalConfig
    from hub.leitor import Leitor
    canal = CanalConfig(
        ch=2, sensor_id='TEMP-HENKE', area_id='AREA-EXPURGO',
        tipo_medida='temperatura', unidade='C', protocolo_origem='modbus',
        map_in=None, map_out=None,
    )
    leitor = object.__new__(Leitor)
    from hub import modbus_backend
    leitor._backend = modbus_backend
    # _specs NÃO deve incluir o canal sem map:
    assert leitor._specs([canal]) == []


def test_ler_todos_canal_sem_map_reporta_valor_nativo_ok(tmp_path):
    """Canal sem 'map:' (ex.: RS-485 nativo) tem que atravessar ler_todos com o
    valor nativo intacto e status "ok" — sem passar por MapSpec algum.

    Esta é a regressão do bug que motivou a branch: um map:[0,0] degenerado
    zerava a leitura do sensor. _specs já exclui canais sem map (testado em
    test_canal_sem_map_preserva_valor_nativo), mas nada garantia que
    ler_todos, ao consumir a entrada crua do driver via por_canal, preservasse
    o valor nativo em vez de zerá-lo.
    """
    driver = _DriverFake([{"channel": 2, "value": 25.9, "unit": "C"}])
    leitor = Leitor(_cfg_sem_map(tmp_path), backend=_BackendFake(driver))
    leituras = leitor.ler_todos(datetime(2026, 7, 24, 0, 1, tzinfo=TZ))

    assert len(leituras) == 1
    r = leituras[0]
    assert r["sensor_id"] == "SNR-RS-NATIVO"
    assert r["valor"] == 25.9
    assert r["status_leitura"] == "ok"


CFG_GENERICO = """
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
          - endereco: 3
            driver: generico
            canais:
              - ch: 1
                sensor_id: SNR-GEN-01
                area_id: AREA-EXPURGO
                tipo_medida: umidade
                unidade: '%RH'
                protocolo_origem: modbus
                registro: {address: 1, function: 3, data_type: int16, scale: 0.1, offset: 0.0, count: 1}
"""


def _cfg_generico(tmp_path):
    p = tmp_path / "c_generico.yaml"
    p.write_text(textwrap.dedent(CFG_GENERICO))
    return config.carregar_config(p)


def test_leitor_deriva_registros_dos_canais_e_repassa_a_criar_driver(tmp_path):
    driver = _DriverFake([{"channel": 1, "value": 5.1, "unit": "%RH"}])
    backend = _BackendRegistrosFake(driver)
    Leitor(_cfg_generico(tmp_path), backend=backend)
    assert backend.registros_recebido == [
        {'ch': 1, 'address': 1, 'function': 3, 'data_type': 'int16',
         'scale': 0.1, 'offset': 0.0, 'count': 1},
    ]


def test_leitor_com_driver_sem_registro_passa_registros_none(tmp_path):
    driver = _DriverFake()
    backend = _BackendRegistrosFake(driver)
    Leitor(_cfg(tmp_path), backend=backend)
    assert backend.registros_recebido is None


CFG_FAIXA = """
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
                sensor_id: SNR-HENKE
                area_id: AREA-EXPURGO
                tipo_medida: temperatura
                unidade: C
                protocolo_origem: modbus
                faixa_min: 0.1
                faixa_max: 100
              - ch: 2
                sensor_id: SNR-DENTRO
                area_id: AREA-EXPURGO
                tipo_medida: temperatura
                unidade: C
                protocolo_origem: modbus
                faixa_min: 0.1
                faixa_max: 100
              - ch: 3
                sensor_id: SNR-SEMFAIXA
                area_id: AREA-EXPURGO
                tipo_medida: temperatura
                unidade: C
                protocolo_origem: modbus
"""


def _cfg_faixa(tmp_path):
    p = tmp_path / "c_faixa.yaml"
    p.write_text(textwrap.dedent(CFG_FAIXA))
    return config.carregar_config(p)


def test_valor_fora_da_faixa_vira_suspeito(tmp_path):
    # ch1 tem faixa [0.1, 100] e o driver fake devolve 0.0 -> fora da faixa -> suspeito
    # ch2 tem a mesma faixa e o driver devolve 50.0 (dentro) -> ok
    # ch3 nao tem faixa configurada e o driver devolve 999.0 (fora de qualquer faixa
    # razoavel) -> sem gate, comportamento inalterado -> ok
    driver = _DriverFake([
        {"channel": 1, "value": 0.0, "unit": "C"},
        {"channel": 2, "value": 50.0, "unit": "C"},
        {"channel": 3, "value": 999.0, "unit": "C"},
    ])
    leitor = Leitor(_cfg_faixa(tmp_path), backend=_BackendFake(driver))
    leituras = leitor.ler_todos(datetime(2026, 7, 24, 0, 1, tzinfo=TZ))
    por_sensor = {r["sensor_id"]: r for r in leituras}

    leitura_henke = por_sensor["SNR-HENKE"]
    assert leitura_henke["status_leitura"] == "suspeito"
    assert leitura_henke["valor"] == 0.0  # valor real preservado

    leitura_dentro = por_sensor["SNR-DENTRO"]
    assert leitura_dentro["status_leitura"] == "ok"
    assert leitura_dentro["valor"] == 50.0

    leitura_sem_faixa = por_sensor["SNR-SEMFAIXA"]
    assert leitura_sem_faixa["status_leitura"] == "ok"
    assert leitura_sem_faixa["valor"] == 999.0


CFG_FAIXA_CALIBRACAO = """
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
                sensor_id: SNR-CORRIGIDO-FORA
                area_id: AREA-EXPURGO
                tipo_medida: temperatura
                unidade: C
                protocolo_origem: modbus
                faixa_min: 0.1
                faixa_max: 100
                calibracao: {ganho: 10.0, offset: 5.0}
              - ch: 2
                sensor_id: SNR-CORRIGIDO-DENTRO
                area_id: AREA-EXPURGO
                tipo_medida: temperatura
                unidade: C
                protocolo_origem: modbus
                faixa_min: 0.1
                faixa_max: 100
                calibracao: {ganho: 0.5, offset: 0}
"""


def _cfg_faixa_calibracao(tmp_path):
    p = tmp_path / "c_faixa_cal.yaml"
    p.write_text(textwrap.dedent(CFG_FAIXA_CALIBRACAO))
    return config.carregar_config(p)


def test_gate_de_faixa_atua_sobre_valor_corrigido_nao_sobre_bruto(tmp_path):
    """O gate de faixa (`_fora_da_faixa`) tem que checar o valor JA calibrado
    (ganho*bruto+offset), nao o bruto que veio do driver.

    ch1: bruto=15.0 (dentro de [0.1,100] se olhado cru) mas calibracao
    ganho=10.0/offset=5.0 -> corrigido = 10*15+5 = 155.0, fora da faixa ->
    suspeito. Se o gate checasse o bruto, este caso passaria como "ok" --
    errado.

    ch2: bruto=150.0 (fora da faixa crua) mas calibracao ganho=0.5/offset=0
    -> corrigido = 0.5*150 = 75.0, dentro da faixa -> ok. Prova o sentido
    inverso: nao marcar suspeito so porque o bruto pareceria fora.
    """
    driver = _DriverFake([
        {"channel": 1, "value": 15.0, "unit": "C"},
        {"channel": 2, "value": 150.0, "unit": "C"},
    ])
    leitor = Leitor(_cfg_faixa_calibracao(tmp_path), backend=_BackendFake(driver))
    leituras = leitor.ler_todos(datetime(2026, 7, 24, 0, 1, tzinfo=TZ))
    por_sensor = {r["sensor_id"]: r for r in leituras}

    fora = por_sensor["SNR-CORRIGIDO-FORA"]
    assert fora["status_leitura"] == "suspeito"
    assert fora["valor"] == 155.0

    dentro = por_sensor["SNR-CORRIGIDO-DENTRO"]
    assert dentro["status_leitura"] == "ok"
    assert dentro["valor"] == 75.0


CFG_RECONEXAO = """
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
            reconexao_n: 2
            reconexao_m: 2
            reconexao_k: 2
            canais:
              - ch: 1
                sensor_id: SNR-RECONEXAO
                area_id: AREA-EXPURGO
                tipo_medida: temperatura
                unidade: C
                protocolo_origem: modbus
                faixa_min: 0.1
                faixa_max: 100
"""


def _cfg_reconexao(tmp_path):
    p = tmp_path / "c_reconexao.yaml"
    p.write_text(textwrap.dedent(CFG_RECONEXAO))
    return config.carregar_config(p)


class _DriverFaixa:
    """Devolve sempre o mesmo valor (bom ou ruim, conforme gate de faixa do
    canal) e conta close(). Opcionalmente lança em close() (fd que nao fecha
    limpo), pra testar que a reconexao engole essa excecao."""
    def __init__(self, valor, erro_close=False):
        self._valor = valor
        self._erro_close = erro_close
        self.closes = 0
    def ler(self, maps=None):
        return [{"channel": 1, "value": self._valor, "unit": "C"}]
    def close(self):
        self.closes += 1
        if self._erro_close:
            raise RuntimeError("close falhou (fd travado)")


class _DriverPadrao:
    """Cicla por uma sequencia fixa de valores a cada chamada de ler(),
    repetindo do inicio ao esgotar. Usado pra simular flapping (ruim, ok,
    ruim, ok, ...) no MESMO driver, sem depender de reconexao."""
    def __init__(self, valores):
        self._valores = valores
        self._i = 0
    def ler(self, maps=None):
        v = self._valores[self._i % len(self._valores)]
        self._i += 1
        return [{"channel": 1, "value": v, "unit": "C"}]
    def close(self):
        pass


class _DriverFechavel:
    """Simula um fd que, apos close(), estoura em qualquer leitura
    subsequente (fd realmente fechado, nao so 'trocado')."""
    def __init__(self, valor):
        self._valor = valor
        self._fechado = False
        self.closes = 0
    def ler(self, maps=None):
        if self._fechado:
            raise RuntimeError("fd fechado")
        return [{"channel": 1, "value": self._valor, "unit": "C"}]
    def close(self):
        self._fechado = True
        self.closes += 1


class _BackendReconexao:
    """Backend fake: conta chamadas de criar_driver, devolve drivers de uma
    lista (um por chamada, repete o ultimo), e opcionalmente estoura a partir
    de uma certa chamada (simula porta que nao reabre)."""
    def __init__(self, drivers, falha_a_partir=None):
        self._drivers = list(drivers)
        self._falha_a_partir = falha_a_partir
        self.criacoes = 0
        from hub.modbus_backend import MapSpec
        self.MapSpec = MapSpec
    def criar_driver(self, *a, registros=None, **k):
        self.criacoes += 1
        if self._falha_a_partir is not None and self.criacoes >= self._falha_a_partir:
            raise RuntimeError("porta indisponivel")
        idx = min(self.criacoes - 1, len(self._drivers) - 1)
        return self._drivers[idx]


def test_reconecta_apos_n_falhas_seguidas(tmp_path):
    ruim = _DriverFaixa(0.0)
    backend = _BackendReconexao([ruim])
    leitor = Leitor(_cfg_reconexao(tmp_path), backend=backend)
    agora = datetime(2026, 7, 24, 0, 1, tzinfo=TZ)
    assert backend.criacoes == 1  # construcao inicial

    leitor.ler_todos(agora)  # ciclo 1: ruim (suspeito), falhas_seguidas=1 (< n=2)
    assert backend.criacoes == 1

    leitor.ler_todos(agora)  # ciclo 2: ruim, falhas_seguidas=2 >= n=2 -> reconecta
    assert backend.criacoes == 2
    assert ruim.closes == 1


def test_ciclo_ok_zera_contadores_de_reconexao(tmp_path):
    ruim = _DriverFaixa(0.0)
    bom = _DriverFaixa(50.0)
    backend = _BackendReconexao([ruim, bom])
    leitor = Leitor(_cfg_reconexao(tmp_path), backend=backend)
    agora = datetime(2026, 7, 24, 0, 1, tzinfo=TZ)

    leitor.ler_todos(agora)  # ciclo 1: ruim
    leitor.ler_todos(agora)  # ciclo 2: ruim -> reconecta, driver passa a ser `bom`
    assert backend.criacoes == 2

    leituras = leitor.ler_todos(agora)  # ciclo 3: usa driver bom -> ok, contadores zeram
    assert leituras[0]["status_leitura"] == "ok"

    leitor.ler_todos(agora)  # ciclo 4: ainda bom -> nao reconecta de novo
    assert backend.criacoes == 2


def test_teto_m_entra_cooldown_e_retenta_a_cada_k(tmp_path):
    ruim = _DriverFaixa(0.0)
    backend = _BackendReconexao([ruim])  # sempre devolve o mesmo driver ruim
    leitor = Leitor(_cfg_reconexao(tmp_path), backend=backend)
    agora = datetime(2026, 7, 24, 0, 1, tzinfo=TZ)

    # n=2, m=2: cada bloco de 2 ciclos ruins gera 1 reconexao; a 3a reconexao
    # (apos 6 ciclos ruins) estoura o teto m=2 e entra em cooldown k=2.
    for _ in range(6):
        leitor.ler_todos(agora)
    assert backend.criacoes == 3  # init + 2 reconexoes concedidas

    leituras = leitor.ler_todos(agora)  # ciclo 7: em cooldown (k=2 -> 1)
    assert leituras[0]["status_leitura"] == "sensor_offline"
    assert backend.criacoes == 3  # nao tenta reconectar ainda

    leitor.ler_todos(agora)  # ciclo 8: cooldown expira (1 -> 0) -> retenta reconectar
    assert backend.criacoes == 4


def test_falha_ao_recriar_driver_vira_offline_sem_crash(tmp_path):
    ruim = _DriverFechavel(0.0)
    backend = _BackendReconexao([ruim], falha_a_partir=2)
    leitor = Leitor(_cfg_reconexao(tmp_path), backend=backend)
    agora = datetime(2026, 7, 24, 0, 1, tzinfo=TZ)

    leitor.ler_todos(agora)  # ciclo 1: ruim, falhas_seguidas=1
    leituras2 = leitor.ler_todos(agora)  # ciclo 2: ruim -> tenta reconectar, criar_driver estoura
    assert leituras2[0]["status_leitura"] == "suspeito"  # ainda leu do driver antigo, antes do close

    # ler_todos nao propagou a excecao do criar_driver; driver antigo ficou
    # fechado (self._fechado=True) e volta a ser usado no proximo ciclo:
    leituras3 = leitor.ler_todos(agora)  # ciclo 3: driver antigo fechado -> ler() explode
    assert leituras3[0]["status_leitura"] == "sensor_offline"


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


def test_flapping_bad_ok_bad_nao_reconecta(tmp_path):
    """Device flapping: alterna ciclo ruim (fora de faixa) e ciclo ok, sem
    nunca acumular N=2 ciclos ruins SEGUIDOS. O ciclo ok tem que zerar
    falhas_seguidas (e reconexoes) — senão o acumulo atravessa os ciclos ok
    e dispara reconexao espuria num sensor que so esta intermitente.

    N=2 (config _cfg_reconexao). Padrao [ruim, ok, ruim, ok, ...]: cada ruim
    isolado leva falhas_seguidas a 1 (< n=2, sem reconectar); o ok seguinte
    zera. Sem o reset, o 2o ruim ve falhas_seguidas=1 residual do 1o ruim e
    fecha 2 seguidos -> reconecta espuriamente.
    """
    driver = _DriverPadrao([0.0, 50.0])  # 0.0 fora de faixa (suspeito/ruim), 50.0 ok
    backend = _BackendReconexao([driver])
    leitor = Leitor(_cfg_reconexao(tmp_path), backend=backend)
    agora = datetime(2026, 7, 24, 0, 1, tzinfo=TZ)
    assert backend.criacoes == 1  # construcao inicial

    for _ in range(8):  # 4x (ruim, ok)
        leitor.ler_todos(agora)

    assert backend.criacoes == 1  # nenhuma reconexao espuria — flapping nao acumula


def test_close_que_lanca_e_engolido_reconexao_prossegue(tmp_path):
    """close() que lanca (fd travado) durante uma reconexao (apos N ruins)
    tem que ser engolido: ler_todos nao propaga a excecao e a recriacao do
    driver acontece normalmente."""
    ruim = _DriverFaixa(0.0, erro_close=True)
    bom = _DriverFaixa(50.0)
    backend = _BackendReconexao([ruim, bom])
    leitor = Leitor(_cfg_reconexao(tmp_path), backend=backend)
    agora = datetime(2026, 7, 24, 0, 1, tzinfo=TZ)
    assert backend.criacoes == 1

    leitor.ler_todos(agora)  # ciclo 1: ruim, falhas_seguidas=1
    leituras2 = leitor.ler_todos(agora)  # ciclo 2: ruim -> reconecta; close() lanca, engolido
    assert leituras2[0]["status_leitura"] == "suspeito"  # ainda leu do driver antigo, antes do close
    assert backend.criacoes == 2  # recriacao ocorreu apesar do close() ter lancado
    assert ruim.closes == 1  # close() foi chamado (e lancou, mas foi engolido)

    leituras3 = leitor.ler_todos(agora)  # ciclo 3: driver novo (bom) -> confirma reconexao completa
    assert leituras3[0]["status_leitura"] == "ok"
