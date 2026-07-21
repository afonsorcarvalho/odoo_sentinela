import hashlib
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


def carregar_ou_criar_chave(caminho):
    caminho = Path(caminho)
    if caminho.exists():
        return serialization.load_pem_private_key(caminho.read_bytes(), password=None)
    chave = ec.generate_private_key(ec.SECP256R1())
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(chave.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    return chave


def fingerprint_publica(chave_privada):
    chave_publica_der = chave_privada.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    digest = hashlib.sha256(chave_publica_der).hexdigest().upper()
    return ':'.join(digest[i:i + 2] for i in range(0, len(digest), 2))


def assinar(chave_privada, dado_bytes):
    return chave_privada.sign(dado_bytes, ec.ECDSA(hashes.SHA256()))


def verificar_assinatura(chave_publica, assinatura, dado_bytes):
    chave_publica.verify(assinatura, dado_bytes, ec.ECDSA(hashes.SHA256()))
