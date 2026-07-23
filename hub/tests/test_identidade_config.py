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
    # emitidos no topo por api.config_publisher.serializar_config_hub (schema-v2, tenant binding)
    'cliente_id': 'CLI-43', 'site_id': 'SITE-01',
}


def test_fundir_sobrepoe_operacional_sem_vazar_identidade():
    merged = fundir(IDENTIDADE, OPERACIONAL)
    assert merged['intervalo_leitura_s'] == 5
    assert merged['barramentos'] == OPERACIONAL['barramentos']
    assert merged['hub_id'] == 'HUB-0001A2F3'  # identidade preservada
    assert merged['sftp']['username'] == 'hub-x'


def test_fundir_inclui_tenant_do_operacional():
    """cliente_id/site_id vêm do operacional p/ o header assinado ter o tenant (F)."""
    merged = fundir(IDENTIDADE, OPERACIONAL)
    assert merged['cliente_id'] == 'CLI-43'
    assert merged['site_id'] == 'SITE-01'


def test_fundir_tenant_ausente_no_operacional_nao_quebra():
    operacional_sem_tenant = {k: v for k, v in OPERACIONAL.items()
                               if k not in ('cliente_id', 'site_id')}
    merged = fundir(IDENTIDADE, operacional_sem_tenant)
    assert merged['cliente_id'] == '' and merged['site_id'] == ''


def test_efetivo_roundtrip_carrega_tenant_no_hubconfig(tmp_path):
    """Pina o caminho de produção: fundir -> arquivo efetivo -> HubConfig com tenant no header."""
    merged = fundir(IDENTIDADE, OPERACIONAL)
    caminho = tmp_path / 'config.yaml'
    escrever_config_efetivo(merged, str(caminho))
    cfg = config_mod.carregar_config(str(caminho))
    assert cfg.cliente_id == 'CLI-43'
    assert cfg.site_id == 'SITE-01'


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


def test_escrever_config_efetivo_e_atomico_sem_lixo_residual(tmp_path):
    merged = fundir(IDENTIDADE, OPERACIONAL)
    caminho = tmp_path / 'config.yaml'
    escrever_config_efetivo(merged, str(caminho))
    assert caminho.exists()
    assert not (tmp_path / 'config.yaml.tmp').exists()  # rename atômico, sem lixo
