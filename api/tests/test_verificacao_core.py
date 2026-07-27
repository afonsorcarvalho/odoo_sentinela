import io
import tracemalloc
import zipfile
import zlib

import pytest

from api import verificacao


def _zip(entradas):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for nome, dados in entradas:
            z.writestr(nome, dados)
    return buf.getvalue()


def test_coletar_arquivo_avulso():
    itens = verificacao.coletar('a.txt', b'conteudo')
    assert itens == [('a.txt', b'conteudo')]


def test_coletar_zip_lista_entradas():
    z = _zip([('x.txt', b'X'), ('sub/y.txt', b'Y')])
    itens = dict(verificacao.coletar('lote.zip', z))
    assert set(itens) == {'x.txt', 'sub/y.txt'}


def test_coletar_zip_ignora_aninhado_e_diretorio():
    z = _zip([('a.txt', b'A'), ('interno.zip', b'PK\x03\x04qualquer')])
    itens = dict(verificacao.coletar('lote.zip', z))
    assert 'a.txt' in itens and 'interno.zip' not in itens


def test_coletar_zip_estoura_contagem():
    z = _zip([(f'f{i}.txt', b'x') for i in range(verificacao.ARQUIVOS_MAX + 1)])
    with pytest.raises(verificacao.LimiteExcedido):
        verificacao.coletar('lote.zip', z)


def test_coletar_zip_estoura_descomprimido(monkeypatch):
    monkeypatch.setattr(verificacao, 'DESCOMPRIMIDO_MAX', 10)
    z = _zip([('big.txt', b'x' * 100)])
    with pytest.raises(verificacao.LimiteExcedido):
        verificacao.coletar('lote.zip', z)


def _zip_deflated(nome, dados):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(nome, dados)
    return buf.getvalue()


def test_coletar_zip_bomba_nao_decomprime_alem_do_orcamento(monkeypatch):
    """Zip cujo file_size (metadado da central directory) MENTE: declara poucos
    bytes enquanto o payload DEFLATE real tem 50 MB. O guard antigo somava
    info.file_size (valor DECLARADO, nao o real) e so' depois chamava
    z.read(info) sem limite -- que decomprime o payload inteiro antes de
    qualquer checagem. Simulamos a mentira mutando o ZipInfo ja' parseado:
    e' exatamente o que uma central directory adulterada produz na leitura
    real (ZipExtFile usa zinfo.file_size, nao importa a origem do valor).
    CRC tambem e' ajustado para bater com o conteudo truncado que de fato
    sera devolvido, para que a chamada complete sem BadZipFile e o teste
    meca apenas o que importa: o pico de memoria.

    NB: o teste literal do brief (zip honesto, so' com DEFLATE bom) faz
    o guard antigo (soma de info.file_size) barrar ANTES de ler -- nunca
    chega a chamar z.read(info) e portanto passa mesmo no codigo com bug
    (confirmado empiricamente: 1 passed contra o codigo antigo). Por isso
    foi substituido por este, que de fato mente sobre o tamanho e reproduz
    o bypass descrito.
    """
    monkeypatch.setattr(verificacao, 'DESCOMPRIMIDO_MAX', 1_000_000)  # 1 MB
    tamanho_mentiroso = 10
    dados_reais = b'\x00' * 50_000_000  # 50 MB reais, ~50 KB comprimido
    bomba = _zip_deflated('bomba.txt', dados_reais)

    real_infolist = zipfile.ZipFile.infolist

    def infolist_mentiroso(self):
        infos = real_infolist(self)
        for info in infos:
            info.file_size = tamanho_mentiroso
            info.CRC = zlib.crc32(dados_reais[:tamanho_mentiroso])
        return infos

    monkeypatch.setattr(zipfile.ZipFile, 'infolist', infolist_mentiroso)

    tracemalloc.start()
    try:
        verificacao.coletar('lote.zip', bomba)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 10_000_000, f'decomprimiu demais: peak={peak}'


def test_verificar_upload_usa_chaves(monkeypatch, tmp_path):
    # reusa fixture de arquivo assinado do verificador
    from ingestao.tests.test_verificador import _preparar
    caminho, _, assinador = _preparar(tmp_path, selar=True)
    dados = caminho.read_bytes()
    chaves = {'COL-1': assinador.chave_publica_pem()}
    lote = verificacao.verificar_upload('r.txt', dados, chaves_pem=chaves)
    assert lote.validos == 1 and lote.todos_ok is True
