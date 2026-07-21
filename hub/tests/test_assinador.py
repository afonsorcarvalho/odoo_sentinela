from contrato import identidade
from hub.assinador import AssinadorSoftware


def test_assina_e_verifica(tmp_path):
    ass = AssinadorSoftware(tmp_path / "k.pem")
    dado = b"hash-final-de-teste"
    assinatura = ass.assinar(dado)
    chave_pub = identidade.carregar_ou_criar_chave(tmp_path / "k.pem").public_key()
    identidade.verificar_assinatura(chave_pub, assinatura, dado)  # não levanta = ok


def test_fingerprint_estavel(tmp_path):
    ass = AssinadorSoftware(tmp_path / "k.pem")
    assert ass.fingerprint() == ass.fingerprint()
    assert ":" in ass.fingerprint()


def test_expoe_chave_publica_pem(tmp_path):
    ass = AssinadorSoftware(tmp_path / "k.pem")
    pem = ass.chave_publica_pem()
    assert pem.startswith("-----BEGIN PUBLIC KEY-----")
