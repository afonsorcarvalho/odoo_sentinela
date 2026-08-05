import io
import stat as stat_mod
from datetime import date

import pytest

from api.arquivos import ParametroInvalido, caminho_do_dia, listar_arquivos_do_dia, validar_token


class FakeAttr:
    """Imita paramiko.SFTPAttributes no que listar_arquivos_do_dia usa."""

    def __init__(self, filename, tamanho=0, tipo='arquivo'):
        self.filename = filename
        self.st_size = tamanho
        modos = {
            'arquivo': stat_mod.S_IFREG | 0o644,
            'dir': stat_mod.S_IFDIR | 0o755,
            'link': stat_mod.S_IFLNK | 0o777,
        }
        self.st_mode = modos[tipo]


class FakeSFTP:
    """SFTP falso: um dict de caminho absoluto -> bytes.

    Diretórios são inferidos dos caminhos. Levanta IOError em pasta
    inexistente, igual ao paramiko.
    """

    def __init__(self, arquivos):
        self.arquivos = dict(arquivos)
        self.links = set()

    def listdir_attr(self, caminho):
        caminho = caminho.rstrip('/')
        filhos = {}
        for full in self.arquivos:
            if not full.startswith(caminho + '/'):
                continue
            resto = full[len(caminho) + 1:]
            nome = resto.split('/')[0]
            if '/' in resto:
                filhos[nome] = FakeAttr(nome, 0, 'dir')
            else:
                tipo = 'link' if full in self.links else 'arquivo'
                filhos[nome] = FakeAttr(nome, len(self.arquivos[full]), tipo)
        if not filhos:
            raise IOError(f'No such file: {caminho}')
        return list(filhos.values())

    def open(self, caminho, modo='r'):
        if caminho not in self.arquivos:
            raise IOError(f'No such file: {caminho}')
        return io.BytesIO(self.arquivos[caminho])


def test_validar_token_aceita_codigos_reais():
    assert validar_token('CLI-43') == 'CLI-43'
    assert validar_token('SITE-DEMO-01') == 'SITE-DEMO-01'
    assert validar_token('HUB_0001A2F3') == 'HUB_0001A2F3'


@pytest.mark.parametrize('valor', [
    '..',
    '../..',
    'a/b',
    'CLI-43/../../etc',
    '%2e%2e',
    'cli 43',
    '',
    'x' * 65,
    'CLI-43\n',
    '\nCLI-43',
    'CLI-43\r\n',
])
def test_validar_token_recusa_travessia_e_lixo(valor):
    # A defesa contra path traversal mora aqui: se um destes passar, o caminho
    # montado em caminho_do_dia escapa da raiz do acervo.
    with pytest.raises(ParametroInvalido):
        validar_token(valor)


def test_caminho_do_dia_monta_arvore_do_acervo():
    assert caminho_do_dia('/uploads', 'CLI-43', 'SITE-DEMO-01', date(2026, 7, 29)) == \
        '/uploads/CLI-43/2026/07/29/SITE-DEMO-01'


def test_caminho_do_dia_zero_pad_mes_e_dia():
    assert caminho_do_dia('/uploads', 'CLI-1', 'S-1', date(2026, 1, 5)) == \
        '/uploads/CLI-1/2026/01/05/S-1'


def test_caminho_do_dia_valida_os_tokens():
    with pytest.raises(ParametroInvalido):
        caminho_do_dia('/uploads', '../etc', 'S-1', date(2026, 1, 5))


RAIZ = '/uploads/CLI-43/2026/07/29/SITE-DEMO-01'


def _acervo_de_um_dia():
    return FakeSFTP({
        f'{RAIZ}/HUB-0001/COL-BUS0/2026-07-29_HUB-0001-COL-BUS0_leituras.txt': b'linha1\nlinha2\n',
        f'{RAIZ}/HUB-0001/COL-BUS0/2026-07-29_HUB-0001-COL-BUS0_alarmes.txt': b'alarme\n',
        f'{RAIZ}/HUB-0001/COL-BUS1/2026-07-29_HUB-0001-COL-BUS1_leituras.txt': b'x' * 100,
    })


def test_listar_traz_caminho_relativo_e_tamanho():
    encontrados = listar_arquivos_do_dia(_acervo_de_um_dia(), RAIZ)
    assert encontrados == [
        ('HUB-0001/COL-BUS0/2026-07-29_HUB-0001-COL-BUS0_alarmes.txt', 7),
        ('HUB-0001/COL-BUS0/2026-07-29_HUB-0001-COL-BUS0_leituras.txt', 14),
        ('HUB-0001/COL-BUS1/2026-07-29_HUB-0001-COL-BUS1_leituras.txt', 100),
    ]


def test_listar_pasta_inexistente_devolve_vazio():
    assert listar_arquivos_do_dia(FakeSFTP({}), RAIZ) == []


def test_listar_ignora_arquivo_fundo_demais():
    # HUB/COLETOR/arquivo = 3 níveis. Qualquer coisa mais funda não faz parte
    # da convenção do acervo e não entra no ZIP.
    sftp = FakeSFTP({
        f'{RAIZ}/HUB-0001/COL-BUS0/subpasta/inesperado.txt': b'nao',
        f'{RAIZ}/HUB-0001/COL-BUS0/ok.txt': b'sim',
    })
    assert listar_arquivos_do_dia(sftp, RAIZ) == [('HUB-0001/COL-BUS0/ok.txt', 3)]


def test_listar_ignora_symlink():
    sftp = FakeSFTP({
        f'{RAIZ}/HUB-0001/COL-BUS0/real.txt': b'sim',
        f'{RAIZ}/HUB-0001/COL-BUS0/atalho.txt': b'nao',
    })
    sftp.links.add(f'{RAIZ}/HUB-0001/COL-BUS0/atalho.txt')
    assert listar_arquivos_do_dia(sftp, RAIZ) == [('HUB-0001/COL-BUS0/real.txt', 3)]
