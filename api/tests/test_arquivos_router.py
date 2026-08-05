import hashlib
import io
import stat as stat_mod
import zipfile

import pytest
from fastapi.testclient import TestClient

from api import arquivos_router
from api.main import app

SECRET = 'segredo-de-teste'
RAIZ = '/uploads/CLI-43/2026/07/29/SITE-DEMO-01'
LEITURAS = b'ts;sensor;valor\n2026-07-29T00:00:00;SNR-1;21.5\n#assinatura=abc\n'


class FakeAttr:
    def __init__(self, filename, tamanho=0, tipo='arquivo'):
        self.filename = filename
        self.st_size = tamanho
        self.st_mode = {'arquivo': stat_mod.S_IFREG | 0o644,
                        'dir': stat_mod.S_IFDIR | 0o755}[tipo]


class FakeSFTP:
    def __init__(self, arquivos):
        self.arquivos = dict(arquivos)

    def listdir_attr(self, caminho):
        caminho = caminho.rstrip('/')
        filhos = {}
        for full in self.arquivos:
            if not full.startswith(caminho + '/'):
                continue
            resto = full[len(caminho) + 1:]
            nome = resto.split('/')[0]
            filhos[nome] = (FakeAttr(nome, 0, 'dir') if '/' in resto
                            else FakeAttr(nome, len(self.arquivos[full])))
        if not filhos:
            raise IOError('No such file')
        return list(filhos.values())

    def open(self, caminho, modo='r'):
        return io.BytesIO(self.arquivos[caminho])

    def close(self):
        pass


class FakeTransport:
    def close(self):
        pass


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setattr(arquivos_router, '_SECRET', SECRET)
    monkeypatch.setattr(arquivos_router, 'SFTP_UPLOADS', '/uploads')
    monkeypatch.setattr(arquivos_router, 'MAX_BYTES', 500 * 1024 * 1024)
    sftp = FakeSFTP({f'{RAIZ}/HUB-0001/COL-BUS0/leituras.txt': LEITURAS})
    monkeypatch.setattr(arquivos_router, '_sftp_conectar', lambda: (FakeTransport(), sftp))
    return TestClient(app)


def _url(cliente_id='CLI-43', site='SITE-DEMO-01', data='2026-07-29'):
    return f'/internal/arquivos/zip?cliente={cliente_id}&site={site}&data={data}'


def test_sem_secret_401(cliente):
    assert cliente.get(_url()).status_code == 401


def test_secret_errado_401(cliente):
    r = cliente.get(_url(), headers={'X-Config-Secret': 'outro'})
    assert r.status_code == 401


def test_cliente_com_travessia_400(cliente):
    r = cliente.get(_url(cliente_id='../../etc'), headers={'X-Config-Secret': SECRET})
    assert r.status_code == 400


def test_data_nao_iso_400(cliente):
    r = cliente.get(_url(data='29-07-2026'), headers={'X-Config-Secret': SECRET})
    assert r.status_code == 400


def test_dia_sem_arquivo_404(cliente):
    r = cliente.get(_url(data='2026-07-01'), headers={'X-Config-Secret': SECRET})
    assert r.status_code == 404


def test_acima_do_teto_413(cliente, monkeypatch):
    monkeypatch.setattr(arquivos_router, 'MAX_BYTES', 10)
    r = cliente.get(_url(), headers={'X-Config-Secret': SECRET})
    assert r.status_code == 413


def test_zip_do_dia_com_bytes_intactos(cliente):
    r = cliente.get(_url(), headers={'X-Config-Secret': SECRET})
    assert r.status_code == 200
    assert r.headers['content-type'] == 'application/zip'
    assert 'sentinela_SITE-DEMO-01_2026-07-29.zip' in r.headers['content-disposition']
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert zf.namelist() == ['HUB-0001/COL-BUS0/leituras.txt']
        assert hashlib.sha256(zf.read('HUB-0001/COL-BUS0/leituras.txt')).hexdigest() == \
            hashlib.sha256(LEITURAS).hexdigest()
