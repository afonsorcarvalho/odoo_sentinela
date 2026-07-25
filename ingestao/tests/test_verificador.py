from datetime import datetime

from cryptography.hazmat.primitives.asymmetric import ec

from contrato import identidade
from hub.arquivo_diario import ArquivoDiario
from hub.assinador import AssinadorSoftware
from ingestao import registro_coletores, verificador


def test_fingerprint_de_publica_bate_com_fingerprint_privada():
    chave = ec.generate_private_key(ec.SECP256R1())
    assert identidade.fingerprint_de_publica(chave.public_key()) == identidade.fingerprint_publica(chave)


def _leitura(ts, valor=96.83):
    return {'timestamp': ts, 'sensor_id': 'SNR-1', 'area_id': 'EXPURGO',
            'tipo_medida': 'temperatura', 'valor': valor, 'unidade': 'C',
            'protocolo_origem': '4-20ma', 'status_leitura': 'ok',
            'cert_ver': 3, 'cal_ganho': 0.965, 'cal_offset': 0.33}


def _preparar(tmp_path, selar=True):
    assinador = AssinadorSoftware(str(tmp_path / "k.pem"))
    arq = ArquivoDiario('COL-1', 'HUB-1', '2.3.1', '-03:00', str(tmp_path / "d"),
                        assinador, cliente_id='CLI-1', site_id='SITE-1')
    arq.registrar(_leitura(datetime(2026, 7, 16, 0, 1, 0)))
    arq.registrar(_leitura(datetime(2026, 7, 16, 0, 2, 0)))
    if selar:
        arq.selar('2026-07-16')
    registro = str(tmp_path / "reg.json")
    registro_coletores.registrar_coletor(registro, 'COL-1', assinador.chave_publica_pem())
    return arq.caminho('2026-07-16'), registro, assinador


def _bytes(caminho):
    return ('arquivo.txt', open(caminho, 'rb').read())


def test_modo_a_arquivo_valido(tmp_path):
    caminho, registro, _ = _preparar(tmp_path, selar=True)
    lote = verificador.verificar_itens([_bytes(caminho)], registro_path=registro)
    assert lote.total == 1 and lote.validos == 1 and lote.todos_ok is True
    item = lote.itens[0]
    assert item.estado == 'valido'
    assert item.coletor_id == 'COL-1'
    assert item.total_linhas == 2
    assert item.fingerprint_conferido is None  # modo A não confere fingerprint


def test_modo_a_linha_adulterada_e_invalido(tmp_path):
    caminho, registro, _ = _preparar(tmp_path, selar=True)
    linhas = caminho.read_text().split('\n')
    i = next(i for i, l in enumerate(linhas) if l and not l.startswith('#'))
    campos = linhas[i].split('|'); campos[5] = '999.99'; linhas[i] = '|'.join(campos)
    caminho.write_text('\n'.join(linhas))
    lote = verificador.verificar_itens([_bytes(caminho)], registro_path=registro)
    assert lote.invalidos == 1 and lote.todos_ok is False
    assert lote.itens[0].estado == 'invalido'


def test_modo_a_sem_footer_e_incompleto(tmp_path):
    caminho, registro, _ = _preparar(tmp_path, selar=False)
    lote = verificador.verificar_itens([_bytes(caminho)], registro_path=registro)
    assert lote.incompletos == 1 and lote.todos_ok is False
    assert lote.itens[0].estado == 'incompleto'


def test_modo_a_coletor_nao_registrado_e_indeterminado(tmp_path):
    caminho, _, _ = _preparar(tmp_path, selar=True)
    registro_vazio = str(tmp_path / "vazio.json")
    lote = verificador.verificar_itens([_bytes(caminho)], registro_path=registro_vazio)
    assert lote.indeterminados == 1 and lote.todos_ok is False
    item = lote.itens[0]
    assert item.estado == 'indeterminado'
    assert 'não registrado' in item.motivo


def test_nao_e_arquivo_assinado_e_indeterminado(tmp_path):
    caminho = tmp_path / "qualquer.txt"
    caminho.write_text("isto nao e um arquivo assinado\n")
    lote = verificador.verificar_itens([_bytes(caminho)], registro_path=str(tmp_path / "reg.json"))
    assert lote.indeterminados == 1
    assert lote.itens[0].estado == 'indeterminado'


def test_bytes_nao_decodificaveis_e_indeterminado(tmp_path):
    lote = verificador.verificar_itens([('bin.txt', b'\xff\xfe\x00\x01')], registro_path=str(tmp_path / "reg.json"))
    assert lote.indeterminados == 1
    assert lote.itens[0].estado == 'indeterminado'


def test_modo_b_pem_correto_valido_com_fingerprint_conferido(tmp_path):
    caminho, _, assinador = _preparar(tmp_path, selar=True)
    pem = assinador.chave_publica_pem().encode()
    lote = verificador.verificar_itens([_bytes(caminho)], pem_bytes=pem)
    item = lote.itens[0]
    assert item.estado == 'valido'
    assert item.fingerprint_conferido is True
    assert lote.todos_ok is True


def test_modo_b_pem_de_outra_chave_e_invalido(tmp_path):
    caminho, _, _ = _preparar(tmp_path, selar=True)
    outro = AssinadorSoftware(str(tmp_path / "outra.pem"))
    lote = verificador.verificar_itens([_bytes(caminho)], pem_bytes=outro.chave_publica_pem().encode())
    item = lote.itens[0]
    assert item.estado == 'invalido'
    assert item.fingerprint_conferido is False
    assert 'fingerprint' in item.motivo


def test_modo_b_pem_ilegivel_levanta_valueerror(tmp_path):
    caminho, _, _ = _preparar(tmp_path, selar=True)
    import pytest
    with pytest.raises(ValueError):
        verificador.verificar_itens([_bytes(caminho)], pem_bytes=b'nao eh pem')
