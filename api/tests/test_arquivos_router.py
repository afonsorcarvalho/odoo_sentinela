import glob
import hashlib
import io
import stat as stat_mod
import tempfile
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
    def __init__(self, arquivos, falhar_no_open_index=None, falhar_no_close=False):
        self.arquivos = dict(arquivos)
        # Conta chamadas a open() — usado para provar que o teto de tamanho
        # é checado a partir dos metadados (st_size), sem baixar nenhum byte.
        self.aberturas = 0
        # Índice (1-based, ordem das chamadas a open()) em que simular uma
        # queda de SFTP no meio da cópia de montar_zip.
        self._falhar_no_open_index = falhar_no_open_index
        self._falhar_no_close = falhar_no_close

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
        self.aberturas += 1
        if self.aberturas == self._falhar_no_open_index:
            raise IOError('SFTP caiu no meio da cópia')
        return io.BytesIO(self.arquivos[caminho])

    def close(self):
        if self._falhar_no_close:
            raise IOError('conexão já caiu')


class FakeTransport:
    def __init__(self, falhar_no_close=False):
        self._falhar_no_close = falhar_no_close

    def close(self):
        if self._falhar_no_close:
            raise IOError('conexão já caiu')


def _preparar(monkeypatch, sftp, transport=None, max_bytes=500 * 1024 * 1024):
    """Fiação comum aos testes: secret/base/teto + troca de _sftp_conectar.

    Cada teste monta seu próprio par (sftp, transport) — os modos de falha
    variam por teste — então isso substitui a fixture `cliente` quando o
    teste precisa inspecionar o fake depois da chamada.
    """
    monkeypatch.setattr(arquivos_router, '_SECRET', SECRET)
    monkeypatch.setattr(arquivos_router, 'SFTP_UPLOADS', '/uploads')
    monkeypatch.setattr(arquivos_router, 'MAX_BYTES', max_bytes)
    monkeypatch.setattr(arquivos_router, '_sftp_conectar',
                        lambda: (transport or FakeTransport(), sftp))
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def tempdir_isolado(tmp_path, monkeypatch):
    """Aponta tempfile.tempdir (e portanto tempfile.gettempdir()) pro
    diretório privado do teste.

    Sem isso, _tempfiles_zip() faz glob no /tmp compartilhado do processo:
    qualquer outro teste (ou processo do sistema) que largue um .zip em
    /tmp no meio da execução faz o assert de igualdade de conjunto flacar,
    sem relação nenhuma com o comportamento sob teste.
    """
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))
    return tmp_path


def _tempfiles_zip():
    """Conjunto de .zip soltos no diretório de temporários agora mesmo."""
    return set(glob.glob(f'{tempfile.gettempdir()}/*.zip'))


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


def test_acima_do_teto_413(monkeypatch):
    # Fixture `cliente` não serve aqui: precisamos inspecionar o fake depois
    # da chamada para provar QUANDO o teto foi checado, não só o status code.
    sftp = FakeSFTP({f'{RAIZ}/HUB-0001/COL-BUS0/leituras.txt': LEITURAS})
    client = _preparar(monkeypatch, sftp, max_bytes=10)
    r = client.get(_url(), headers={'X-Config-Secret': SECRET})
    assert r.status_code == 413
    # O teto vem do st_size do listdir_attr — nenhum arquivo é aberto antes
    # da comparação. Uma implementação que baixasse tudo e só depois
    # comparasse com MAX_BYTES bateria o status code, mas abriria os
    # arquivos: aberturas ficaria > 0.
    assert sftp.aberturas == 0


def test_close_falha_apos_sucesso_nao_deixa_zip_orfao(monkeypatch, tempdir_isolado):
    # sftp.close() e transport.close() levantam DEPOIS que montar_zip já
    # terminou com sucesso — reproduz o gap achado na auto-revisão: sem a
    # proteção no finally, a exceção do close() mascararia o `return
    # FileResponse(...)` e o ZIP completo ficaria em disco sem que o
    # BackgroundTask de limpeza chegasse a ser registrado.
    sftp = FakeSFTP({f'{RAIZ}/HUB-0001/COL-BUS0/leituras.txt': LEITURAS}, falhar_no_close=True)
    transport = FakeTransport(falhar_no_close=True)
    client = _preparar(monkeypatch, sftp, transport=transport)

    antes = _tempfiles_zip()
    r = client.get(_url(), headers={'X-Config-Secret': SECRET})

    assert r.status_code == 200
    assert _tempfiles_zip() == antes, 'ZIP órfão sobrou em disco'


def test_montar_zip_falha_no_meio_nao_deixa_zip_parcial(monkeypatch, tempdir_isolado):
    # Dois arquivos no dia; open() levanta na SEGUNDA chamada — simula o
    # SFTP caindo depois que montar_zip já escreveu o primeiro membro no
    # ZIP parcial. A rota tem que limpar esse tempfile antes de propagar.
    sftp = FakeSFTP({
        f'{RAIZ}/HUB-0001/COL-BUS0/a.txt': LEITURAS,
        f'{RAIZ}/HUB-0001/COL-BUS0/b.txt': LEITURAS,
    }, falhar_no_open_index=2)
    client = _preparar(monkeypatch, sftp)

    antes = _tempfiles_zip()
    r = client.get(_url(), headers={'X-Config-Secret': SECRET})

    assert r.status_code == 500
    assert _tempfiles_zip() == antes, 'ZIP parcial sobrou em disco'


def test_zip_do_dia_com_bytes_intactos(cliente):
    r = cliente.get(_url(), headers={'X-Config-Secret': SECRET})
    assert r.status_code == 200
    assert r.headers['content-type'] == 'application/zip'
    assert 'sentinela_SITE-DEMO-01_2026-07-29.zip' in r.headers['content-disposition']
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert zf.namelist() == ['HUB-0001/COL-BUS0/leituras.txt']
        assert hashlib.sha256(zf.read('HUB-0001/COL-BUS0/leituras.txt')).hexdigest() == \
            hashlib.sha256(LEITURAS).hexdigest()


def test_ler_max_bytes_usa_default_com_env_malformado(monkeypatch):
    # FIX 6: int(os.environ[...]) direto na import time derrubaria TODA a
    # api (live, historico, config-publish) se ARQUIVOS_ZIP_MAX_BYTES viesse
    # com lixo no .env — um typo numa rota vira downtime total. _ler_max_bytes
    # tem que sobreviver e cair no default, não deixar o ValueError propagar.
    monkeypatch.setenv('ARQUIVOS_ZIP_MAX_BYTES', 'not-a-number')
    assert arquivos_router._ler_max_bytes() == arquivos_router._MAX_BYTES_PADRAO


def test_ler_max_bytes_sem_env_usa_default(monkeypatch):
    monkeypatch.delenv('ARQUIVOS_ZIP_MAX_BYTES', raising=False)
    assert arquivos_router._ler_max_bytes() == arquivos_router._MAX_BYTES_PADRAO


def test_ler_max_bytes_respeita_env_valido(monkeypatch):
    monkeypatch.setenv('ARQUIVOS_ZIP_MAX_BYTES', '12345')
    assert arquivos_router._ler_max_bytes() == 12345


def test_secret_correto_com_string_diferente_em_tamanho_ainda_e_401(cliente):
    # hmac.compare_digest não muda o resultado — só a forma como chega lá.
    # Guarda contra uma migração futura que trocasse por comparação manual
    # byte-a-byte com early exit.
    r = cliente.get(_url(), headers={'X-Config-Secret': SECRET + 'x'})
    assert r.status_code == 401
