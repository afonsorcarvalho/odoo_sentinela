import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from ingestao import registro_coletores


def _gerar_chave_privada_pem(tmp_path, nome='chave.pem'):
    chave = ec.generate_private_key(ec.SECP256R1())
    caminho = tmp_path / nome
    caminho.write_bytes(chave.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    return chave, caminho


def test_registrar_e_obter_chave_publica(tmp_path):
    chave, _ = _gerar_chave_privada_pem(tmp_path)
    chave_publica_pem = chave.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    registro_path = tmp_path / 'registro.json'
    registro_coletores.registrar_coletor(registro_path, 'COL-1', chave_publica_pem)
    chave_recuperada = registro_coletores.obter_chave_publica(registro_path, 'COL-1')
    assert chave_recuperada.public_numbers() == chave.public_key().public_numbers()


def test_obter_chave_publica_levanta_erro_para_coletor_nao_registrado(tmp_path):
    registro_path = tmp_path / 'registro.json'
    with pytest.raises(KeyError):
        registro_coletores.obter_chave_publica(registro_path, 'COL-INEXISTENTE')


def test_registrar_a_partir_de_chave_privada(tmp_path):
    chave, caminho_chave = _gerar_chave_privada_pem(tmp_path)
    registro_path = tmp_path / 'registro.json'
    registro_coletores.registrar_a_partir_de_chave_privada(registro_path, caminho_chave, 'COL-2')
    chave_recuperada = registro_coletores.obter_chave_publica(registro_path, 'COL-2')
    assert chave_recuperada.public_numbers() == chave.public_key().public_numbers()


def test_carregar_registro_vazio_quando_arquivo_nao_existe(tmp_path):
    registro_path = tmp_path / 'nao-existe.json'
    assert registro_coletores.carregar_registro(registro_path) == {}


def test_registrar_atualiza_entrada_existente(tmp_path):
    chave1, _ = _gerar_chave_privada_pem(tmp_path, 'chave1.pem')
    chave2, _ = _gerar_chave_privada_pem(tmp_path, 'chave2.pem')
    registro_path = tmp_path / 'registro.json'
    pem1 = chave1.public_key().public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    pem2 = chave2.public_key().public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    registro_coletores.registrar_coletor(registro_path, 'COL-3', pem1)
    registro_coletores.registrar_coletor(registro_path, 'COL-3', pem2)
    chave_recuperada = registro_coletores.obter_chave_publica(registro_path, 'COL-3')
    assert chave_recuperada.public_numbers() == chave2.public_key().public_numbers()
