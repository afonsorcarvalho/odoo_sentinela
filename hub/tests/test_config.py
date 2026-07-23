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


# tenant: obrigatório junto com o bloco sftp (o EnviadorSftp monta
# {cliente}/AAAA/MM/DD/{site}/{hub}/{coletor}/ e não tem como sem eles).
TENANT = """
    cliente_id: CLI-000123
    site_id: SITE-0001
"""


def test_sem_sftp_fica_none(tmp_path):
    cfg = config.carregar_config(_escrever(tmp_path, VALIDA))
    assert cfg.sftp is None


def test_com_sftp_carrega(tmp_path):
    cfg = config.carregar_config(_escrever(tmp_path, VALIDA + TENANT + SFTP_BLOCO))
    assert cfg.sftp.host == "192.168.0.10"
    assert cfg.sftp.port == 2022
    assert cfg.sftp.username == "hub-0001A2F3"
    assert cfg.sftp.remote_dir == "/uploads"


def test_sftp_sem_host_falha(tmp_path):
    ruim = (VALIDA + TENANT
            + SFTP_BLOCO.replace("host: 192.168.0.10", "port: 2022"))
    with pytest.raises(ValueError, match="sftp.host"):
        config.carregar_config(_escrever(tmp_path, ruim))


# --- FIX C4: segmento de tenant inválido matava o processo do Hub ---
# _caminho_remoto chama validar_segmento_path FORA do try/except do varrer: o
# ValueError subia por varrer() -> executar() e derrubava o Hub (parava de ler
# sensores) horas depois do boot, no primeiro arquivo selado. cliente_id/site_id
# eram opcionais com default '' e o config.example.yaml não os trazia, então
# `segmento de path inválido: ''` era o caminho normal, não o excepcional.


def test_sftp_sem_cliente_id_falha_no_carregar_config(tmp_path):
    ruim = VALIDA + "    site_id: SITE-0001\n" + SFTP_BLOCO
    with pytest.raises(ValueError, match="cliente_id"):
        config.carregar_config(_escrever(tmp_path, ruim))


def test_sftp_sem_site_id_falha_no_carregar_config(tmp_path):
    ruim = VALIDA + "    cliente_id: CLI-000123\n" + SFTP_BLOCO
    with pytest.raises(ValueError, match="site_id"):
        config.carregar_config(_escrever(tmp_path, ruim))


def test_cliente_id_com_barra_falha_no_carregar_config(tmp_path):
    ruim = (VALIDA + TENANT.replace("CLI-000123", "CLI/000123") + SFTP_BLOCO)
    with pytest.raises(ValueError, match="cliente_id"):
        config.carregar_config(_escrever(tmp_path, ruim))


def test_coletor_id_com_barra_falha_no_carregar_config(tmp_path):
    # coletor_id também é diretório LOCAL (ArquivoDiario/EnviadorSftp): validar
    # na entrada cobre local e remoto de uma vez (Minor #1 do review).
    ruim = VALIDA.replace("coletor_id: COL-RS485-BUS0", "coletor_id: ../escapa")
    with pytest.raises(ValueError, match="coletor_id"):
        config.carregar_config(_escrever(tmp_path, ruim))


def test_hub_id_com_barra_falha_no_carregar_config(tmp_path):
    ruim = VALIDA.replace("hub_id: HUB-0001", "hub_id: HUB/0001")
    with pytest.raises(ValueError, match="hub_id"):
        config.carregar_config(_escrever(tmp_path, ruim))


# --- FIX: _validar_segmento coagia com str(valor) antes de validar, então
# None (campo em branco no YAML) e bool viravam 'None'/'False' e PASSAVAM na
# validação — o crash fatal que essa validação existe pra evitar só se movia
# para mais tarde (_caminho_remoto ou montar_cabecalho -> validar_identificador
# com o valor bruto ainda None). Ver review: config.yaml preenchido à mão em
# campo, com uma chave presente e valor em branco, produz None no YAML.


def test_cliente_id_em_branco_falha_no_carregar_config(tmp_path):
    ruim = (VALIDA + "    cliente_id:\n    site_id: SITE-0001\n" + SFTP_BLOCO)
    with pytest.raises(ValueError, match="cliente_id"):
        config.carregar_config(_escrever(tmp_path, ruim))


def test_site_id_booleano_falha_no_carregar_config(tmp_path):
    ruim = (VALIDA + "    cliente_id: CLI-000123\n    site_id: false\n" + SFTP_BLOCO)
    with pytest.raises(ValueError, match="site_id"):
        config.carregar_config(_escrever(tmp_path, ruim))


def test_sem_sftp_nao_exige_tenant(tmp_path):
    # hub/config.py também é usado em cenários sem envio (bancada, simulação):
    # sem o bloco sftp ninguém monta caminho remoto, então não há o que exigir.
    cfg = config.carregar_config(_escrever(tmp_path, VALIDA))
    assert cfg.cliente_id == "" and cfg.site_id == ""


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
