import io
import zipfile

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


def test_verificar_upload_usa_chaves(monkeypatch, tmp_path):
    # reusa fixture de arquivo assinado do verificador
    from ingestao.tests.test_verificador import _preparar
    caminho, _, assinador = _preparar(tmp_path, selar=True)
    dados = caminho.read_bytes()
    chaves = {'COL-1': assinador.chave_publica_pem()}
    lote = verificacao.verificar_upload('r.txt', dados, chaves_pem=chaves)
    assert lote.validos == 1 and lote.todos_ok is True
