from cryptography.hazmat.primitives.asymmetric import ec

from contrato import identidade


def test_fingerprint_de_publica_bate_com_fingerprint_privada():
    chave = ec.generate_private_key(ec.SECP256R1())
    assert identidade.fingerprint_de_publica(chave.public_key()) == identidade.fingerprint_publica(chave)
