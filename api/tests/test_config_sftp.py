import os
import paramiko
import pytest

from api.config_publisher import escrever_config_sftp

pytestmark = pytest.mark.skipif(
    not os.environ.get('SFTP_USER'), reason='conta SFTP de serviço não configurada')


def _ler_remoto(caminho):
    t = paramiko.Transport((os.environ['SFTP_HOST'], int(os.environ.get('SFTP_PORT', '2022'))))
    t.connect(username=os.environ['SFTP_USER'],
              pkey=paramiko.Ed25519Key.from_private_key_file(os.environ['SFTP_KEY_PATH']))
    sftp = paramiko.SFTPClient.from_transport(t)
    with sftp.open(caminho, 'r') as f:
        dados = f.read().decode()
    t.close()
    return dados


def test_escrever_config_sftp_grava_arquivo_versionado():
    remoto = escrever_config_sftp('HUB-CFG-01', 9, 'version: 9\n')
    assert remoto == '/config/HUB-CFG-01/config-v9.yaml'
    assert 'version: 9' in _ler_remoto(remoto)
