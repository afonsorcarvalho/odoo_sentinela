import yaml

from hub import config as config_mod
from hub.identidade_config import carregar_identidade, escrever_config_efetivo, fundir

IDENTIDADE = {
    'hub_id': 'HUB-0001A2F3', 'coletor_id': 'COL-RS485-BUS0',
    'firmware_version': '0.1.0', 'timezone_offset': '-03:00',
    'caminho_chave': '~/sentinela-hub/chaves/coletor.pem',
    'caminho_dados': '~/sentinela-hub/dados',
    'mqtt': {'host': 'localhost', 'port': 1883},
    'sftp': {'host': '10.8.0.1', 'port': 2022, 'username': 'hub-x',
             'ssh_key_path': '~/k', 'remote_dir': '/uploads'},
}
OPERACIONAL = {
    'version': 4, 'intervalo_leitura_s': 5,
    'barramentos': [{'porta': '/dev/ttyUSB0', 'baud': 9600, 'paridade': 'N', 'stop_bits': 1,
        'dispositivos': [{'endereco': 1, 'driver': 'n4aib16', 'canais': [
            {'ch': 1, 'sensor_id': 'SNR-EXP-TEMP-01', 'area_id': 'AREA-EXPURGO',
             'tipo_medida': 'temperatura', 'unidade': 'C', 'protocolo_origem': '4-20ma',
             'map': {'in': [4, 20], 'out': [-50, 150]}}]}]}],
}


def test_fundir_sobrepoe_operacional_sem_vazar_identidade():
    merged = fundir(IDENTIDADE, OPERACIONAL)
    assert merged['intervalo_leitura_s'] == 5
    assert merged['barramentos'] == OPERACIONAL['barramentos']
    assert merged['hub_id'] == 'HUB-0001A2F3'  # identidade preservada
    assert merged['sftp']['username'] == 'hub-x'


def test_efetivo_carrega_no_config_py(tmp_path):
    merged = fundir(IDENTIDADE, OPERACIONAL)
    caminho = tmp_path / 'config.yaml'
    escrever_config_efetivo(merged, str(caminho))
    cfg = config_mod.carregar_config(str(caminho))  # não deve levantar
    assert cfg.intervalo_leitura_s == 5
    assert cfg.barramentos[0].dispositivos[0].canais[0].sensor_id == 'SNR-EXP-TEMP-01'
    assert cfg.barramentos[0].dispositivos[0].canais[0].map_in == (4.0, 20.0)


def test_carregar_identidade_le_yaml(tmp_path):
    p = tmp_path / 'identity.yaml'
    p.write_text(yaml.safe_dump(IDENTIDADE))
    assert carregar_identidade(str(p))['hub_id'] == 'HUB-0001A2F3'
