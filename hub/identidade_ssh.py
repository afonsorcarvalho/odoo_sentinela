"""Identidade SSH do Hub para o transporte SFTP (par ed25519).

Separada da chave EC de assinatura (contrato/identidade): esta autentica o
upload no SFTPGo; aquela assina o conteúdo dos arquivos.
"""
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def pubkey_openssh(chave) -> str:
    return chave.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode()


def carregar_ou_criar_chave_ssh(caminho):
    caminho = Path(caminho).expanduser()
    if caminho.exists():
        return serialization.load_ssh_private_key(caminho.read_bytes(), password=None)
    chave = Ed25519PrivateKey.generate()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(chave.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    os.chmod(caminho, 0o600)
    caminho.with_suffix(".pub").write_text(pubkey_openssh(chave) + "\n")
    return chave
