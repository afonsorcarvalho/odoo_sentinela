import os
import paramiko
import pytest

from hub.enviador_sftp import TransporteParamiko

pytestmark = pytest.mark.skipif(
    not os.environ.get('SFTP_USER'), reason='conta SFTP de serviço não configurada')


def _subir(caminho_remoto, conteudo):
    t = paramiko.Transport((os.environ['SFTP_HOST'], int(os.environ.get('SFTP_PORT', '2022'))))
    t.connect(username=os.environ['SFTP_USER'],
              pkey=paramiko.Ed25519Key.from_private_key_file(os.environ['SFTP_KEY_PATH']))
    sftp = paramiko.SFTPClient.from_transport(t)
    try:
        sftp.stat('/config/HUB-BAIXAR')
    except FileNotFoundError:
        sftp.mkdir('/config/HUB-BAIXAR')
    with sftp.open(caminho_remoto, 'w') as f:
        f.write(conteudo)
    t.close()


def test_baixar_traz_arquivo_remoto(tmp_path):
    remoto = '/config/HUB-BAIXAR/config-v3.yaml'
    _subir(remoto, 'version: 3\n')
    transporte = TransporteParamiko(
        os.environ['SFTP_HOST'], int(os.environ.get('SFTP_PORT', '2022')),
        os.environ['SFTP_USER'], os.environ['SFTP_KEY_PATH'], '/uploads')
    destino = tmp_path / 'baixado.yaml'
    transporte.baixar(remoto, str(destino))
    assert destino.read_text() == 'version: 3\n'
