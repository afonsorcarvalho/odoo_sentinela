import textwrap

import pytest

from hub import config


def _escrever(tmp_path, texto):
    caminho = tmp_path / "config.yaml"
    caminho.write_text(textwrap.dedent(texto))
    return caminho


VALIDA = """
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
                map: {in: [4, 20], out: [-50, 150]}
"""


def test_carrega_config_valida(tmp_path):
    cfg = config.carregar_config(_escrever(tmp_path, VALIDA))
    assert cfg.hub_id == "HUB-0001"
    assert cfg.mqtt_port == 1883
    canal = cfg.barramentos[0].dispositivos[0].canais[0]
    assert canal.sensor_id == "SNR-EXP-TEMP-01"
    assert canal.map_in == (4.0, 20.0)
    assert canal.map_out == (-50.0, 150.0)


def test_rejeita_identificador_com_pipe(tmp_path):
    ruim = VALIDA.replace("SNR-EXP-TEMP-01", "SNR|RUIM")
    with pytest.raises(ValueError):
        config.carregar_config(_escrever(tmp_path, ruim))


def test_rejeita_map_com_tamanho_errado(tmp_path):
    ruim = VALIDA.replace("out: [-50, 150]", "out: [-50, 150, 9]")
    with pytest.raises(ValueError):
        config.carregar_config(_escrever(tmp_path, ruim))


SFTP_BLOCO = """
    sftp:
      host: 192.168.0.10
      port: 2022
      username: hub-0001A2F3
      ssh_key_path: /tmp/ssh_hub
      remote_dir: /uploads
"""


def test_sem_sftp_fica_none(tmp_path):
    cfg = config.carregar_config(_escrever(tmp_path, VALIDA))
    assert cfg.sftp is None


def test_com_sftp_carrega(tmp_path):
    cfg = config.carregar_config(_escrever(tmp_path, VALIDA + SFTP_BLOCO))
    assert cfg.sftp.host == "192.168.0.10"
    assert cfg.sftp.port == 2022
    assert cfg.sftp.username == "hub-0001A2F3"
    assert cfg.sftp.remote_dir == "/uploads"


def test_sftp_sem_host_falha(tmp_path):
    ruim = VALIDA + SFTP_BLOCO.replace("host: 192.168.0.10", "port: 2022")
    with pytest.raises(ValueError):
        config.carregar_config(_escrever(tmp_path, ruim))


def test_hubconfig_carrega_tenant_e_calibracao_do_canal(tmp_path):
    from hub import config as config_mod
    yaml_txt = """
hub_id: HUB-1
coletor_id: COL-1
cliente_id: CLI-000123
site_id: SITE-0001
firmware_version: 2.3.1
timezone_offset: "-03:00"
intervalo_leitura_s: 60
caminho_chave: /tmp/k.pem
caminho_dados: /tmp/dados
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
            area_id: EXPURGO
            tipo_medida: temperatura
            unidade: C
            protocolo_origem: 4-20ma
            map: {in: [4, 20], out: [0, 150]}
            calibracao: {cert_ver: 3, ganho: 0.965, offset: 0.33}
"""
    p = tmp_path / "config.yaml"
    p.write_text(yaml_txt)
    cfg = config_mod.carregar_config(str(p))
    assert cfg.cliente_id == 'CLI-000123'
    assert cfg.site_id == 'SITE-0001'
    canal = cfg.barramentos[0].dispositivos[0].canais[0]
    assert canal.calibracao == {'cert_ver': 3, 'ganho': 0.965, 'offset': 0.33}


def test_canal_sem_calibracao_usa_identidade(tmp_path):
    from hub import config as config_mod
    yaml_txt = """
hub_id: HUB-1
coletor_id: COL-1
cliente_id: CLI-1
site_id: SITE-1
firmware_version: 2.3.1
timezone_offset: "-03:00"
intervalo_leitura_s: 60
caminho_chave: /tmp/k.pem
caminho_dados: /tmp/dados
barramentos:
  - porta: /dev/ttyUSB0
    baud: 9600
    paridade: N
    stop_bits: 1
    dispositivos:
      - endereco: 1
        driver: n4aib16
        canais:
          - {ch: 1, sensor_id: SNR-1, area_id: EXPURGO, tipo_medida: temperatura,
             unidade: C, protocolo_origem: 4-20ma, map: {in: [4, 20], out: [0, 150]}}
"""
    p = tmp_path / "config.yaml"
    p.write_text(yaml_txt)
    cfg = config_mod.carregar_config(str(p))
    canal = cfg.barramentos[0].dispositivos[0].canais[0]
    assert canal.calibracao == {'cert_ver': 0, 'ganho': 1.0, 'offset': 0.0}
