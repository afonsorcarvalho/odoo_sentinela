import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ec

from coletor_simulado import identidade


def test_chave_persiste_entre_chamadas(tmp_path):
    caminho = tmp_path / "chave.pem"
    chave1 = identidade.carregar_ou_criar_chave(caminho)
    chave2 = identidade.carregar_ou_criar_chave(caminho)
    assert chave1.private_numbers().private_value == chave2.private_numbers().private_value


def test_fingerprint_deterministico(tmp_path):
    caminho = tmp_path / "chave.pem"
    chave = identidade.carregar_ou_criar_chave(caminho)
    fp1 = identidade.fingerprint_publica(chave)
    fp2 = identidade.fingerprint_publica(chave)
    assert fp1 == fp2
    assert len(fp1.split(':')) == 32  # SHA-256 = 32 bytes


def test_assinatura_verifica_com_chave_correta(tmp_path):
    caminho = tmp_path / "chave.pem"
    chave = identidade.carregar_ou_criar_chave(caminho)
    dado = b"hash_final_de_teste"
    assinatura = identidade.assinar(chave, dado)
    identidade.verificar_assinatura(chave.public_key(), assinatura, dado)


def test_assinatura_falha_com_chave_errada(tmp_path):
    caminho = tmp_path / "chave.pem"
    chave = identidade.carregar_ou_criar_chave(caminho)
    outra_chave = ec.generate_private_key(ec.SECP256R1())
    dado = b"hash_final_de_teste"
    assinatura = identidade.assinar(chave, dado)
    with pytest.raises(InvalidSignature):
        identidade.verificar_assinatura(outra_chave.public_key(), assinatura, dado)
