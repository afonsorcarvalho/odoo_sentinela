import hashlib
import io
import posixpath
import stat as stat_mod
import zipfile
from datetime import date

import pytest

from api.arquivos import ParametroInvalido, caminho_do_dia, listar_arquivos_do_dia, montar_zip, validar_token


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

    def __init__(self, arquivos, falhar_em=()):
        self.arquivos = dict(arquivos)
        self.links = set()
        # Conjunto de caminhos absolutos (sem barra final) cujo listdir_attr
        # deve levantar IOError — imita uma queda de SFTP no meio da árvore,
        # em vez de só "pasta que nunca existiu". Espelha o padrão
        # `falhar_no_open_index` de test_arquivos_router.py.
        self.falhar_em = set(falhar_em)
        # Caminhos (absolutos, sem barra final) cujo listdir_attr deve incluir
        # entradas '.' e '..' na resposta — imita um backend SFTP que devolve
        # os links do próprio diretório, coisa que o sftpgo hoje não faz.
        self.com_dot_dot = set()

    def listdir_attr(self, caminho):
        # normpath: um caller que recursa para 'X/.' ou 'X/..' (por não
        # filtrar essas entradas) precisa cair de volta num diretório REAL do
        # fake — senão o teste do guard '.'/'..' não reproduz a duplicação/
        # travessia de verdade, só um "No such file" inofensivo.
        caminho = posixpath.normpath(caminho)
        if caminho in self.falhar_em:
            raise IOError(f'SFTP caiu ao listar: {caminho}')
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
        resultado = list(filhos.values())
        if caminho in self.com_dot_dot:
            resultado = [FakeAttr('.', 0, 'dir'), FakeAttr('..', 0, 'dir')] + resultado
        return resultado

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


def test_montar_zip_preserva_bytes_e_arvore(tmp_path):
    sftp = _acervo_de_um_dia()
    arquivos = listar_arquivos_do_dia(sftp, RAIZ)
    destino = tmp_path / 'dia.zip'

    montar_zip(sftp, RAIZ, arquivos, str(destino))

    with zipfile.ZipFile(destino) as zf:
        assert sorted(zf.namelist()) == [
            'HUB-0001/COL-BUS0/2026-07-29_HUB-0001-COL-BUS0_alarmes.txt',
            'HUB-0001/COL-BUS0/2026-07-29_HUB-0001-COL-BUS0_leituras.txt',
            'HUB-0001/COL-BUS1/2026-07-29_HUB-0001-COL-BUS1_leituras.txt',
        ]
        for arcname in zf.namelist():
            original = sftp.arquivos[f'{RAIZ}/{arcname}']
            extraido = zf.read(arcname)
            # SHA-256 e não igualdade de string: é o mesmo confronto que o
            # portal de autenticidade faz. Newline normalizado ou BOM
            # inserido quebram aqui, que é onde tem que quebrar.
            assert hashlib.sha256(extraido).hexdigest() == hashlib.sha256(original).hexdigest()


def test_montar_zip_de_arquivo_com_bytes_nao_utf8(tmp_path):
    # O acervo é texto, mas o ZIP não pode presumir isso: qualquer
    # transcodificação silenciosa invalidaria a assinatura.
    cru = b'\x00\xff\xfe raw \r\n sem newline normalizado \r'
    sftp = FakeSFTP({f'{RAIZ}/HUB-X/COL-Y/cru.txt': cru})
    destino = tmp_path / 'cru.zip'

    montar_zip(sftp, RAIZ, listar_arquivos_do_dia(sftp, RAIZ), str(destino))

    with zipfile.ZipFile(destino) as zf:
        assert zf.read('HUB-X/COL-Y/cru.txt') == cru


def test_montar_zip_vazio_gera_zip_valido_sem_membros(tmp_path):
    destino = tmp_path / 'vazio.zip'
    montar_zip(FakeSFTP({}), RAIZ, [], str(destino))
    with zipfile.ZipFile(destino) as zf:
        assert zf.namelist() == []


def test_listar_falha_de_sftp_abaixo_da_raiz_propaga():
    # FIX 1: uma queda de SFTP listando um HUB/COLETOR específico não pode
    # virar lista curta silenciosa — o ZIP sairia completo em aparência e
    # incompleto de fato. Só a pasta do DIA (a raiz) tem direito a virar [].
    sftp = FakeSFTP({
        f'{RAIZ}/HUB-0001/COL-BUS0/leituras.txt': b'ok',
        f'{RAIZ}/HUB-0001/COL-BUS1/leituras.txt': b'sumiu',
    }, falhar_em={f'{RAIZ}/HUB-0001/COL-BUS1'})
    with pytest.raises(IOError):
        listar_arquivos_do_dia(sftp, RAIZ)


def test_listar_pasta_do_dia_ausente_ainda_devolve_vazio_com_falhar_em():
    # A raiz continua tolerante mesmo com o mecanismo de falha presente —
    # não é o parâmetro novo que muda esse comportamento, é o caminho.
    sftp = FakeSFTP({}, falhar_em={RAIZ})
    assert listar_arquivos_do_dia(sftp, RAIZ) == []


def test_listar_ignora_entradas_dot_e_dotdot():
    # FIX 2: '.' duplicaria cada arquivo do diretório; '..' andaria PARA CIMA
    # e fora da raiz — um member '../algo' dentro do ZIP é zip-slip num
    # artefato de auditoria. sftpgo não devolve essas entradas hoje, mas o
    # guard tem que existir mesmo assim.
    #
    # As entradas '.'/'..' ficam no nível HUB (não no COL, que já é a última
    # pasta antes do arquivo): com profundidade_max=3 padrão, a recursão pela
    # entrada '.'/'..' bate no teto exatamente no mesmo nível que o arquivo
    # real, sem sobrar orçamento pra provar duplicação. profundidade_max=4
    # dá esse orçamento e faz o normpath do FakeSFTP resolver '.'/'..' de
    # volta a diretórios REAIS do fake — reproduzindo a duplicação de
    # verdade, não só um "No such file" inofensivo.
    sftp = FakeSFTP({
        f'{RAIZ}/HUB-0001/COL-BUS0/leituras.txt': b'ok',
    })
    sftp.com_dot_dot.add(f'{RAIZ}/HUB-0001')
    encontrados = listar_arquivos_do_dia(sftp, RAIZ, profundidade_max=4)
    assert encontrados == [('HUB-0001/COL-BUS0/leituras.txt', 2)]
    assert all(not rel.startswith('..') for rel, _tam in encontrados)
