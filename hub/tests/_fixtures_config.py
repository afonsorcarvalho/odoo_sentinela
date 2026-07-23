"""Fixtures compartilhadas (IDENTIDADE/OPERACIONAL) — idênticas às da Task 2 (test_identidade_config.py)."""

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
