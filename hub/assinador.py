"""Assinatura do arquivo diário. Interface + implementação em software (EC).

Ponto de extensão: uma implementação ATECC608 futura só precisa satisfazer
o mesmo Protocol, sem tocar o resto do Hub.
"""
from typing import Protocol

from cryptography.hazmat.primitives import serialization

from contrato import identidade


class Assinador(Protocol):
    def fingerprint(self) -> str: ...
    def assinar(self, dado: bytes) -> bytes: ...


class AssinadorSoftware:
    def __init__(self, caminho_chave):
        self._chave = identidade.carregar_ou_criar_chave(caminho_chave)

    def fingerprint(self) -> str:
        return identidade.fingerprint_publica(self._chave)

    def assinar(self, dado: bytes) -> bytes:
        return identidade.assinar(self._chave, dado)

    def chave_publica_pem(self) -> str:
        return self._chave.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
