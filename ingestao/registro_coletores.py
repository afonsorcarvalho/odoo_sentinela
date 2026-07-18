import argparse
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization


def carregar_registro(caminho):
    caminho = Path(caminho)
    if not caminho.exists():
        return {}
    return json.loads(caminho.read_text())


def salvar_registro(caminho, registro):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(registro, indent=2))


def registrar_coletor(caminho, coletor_id, chave_publica_pem):
    registro = carregar_registro(caminho)
    registro[coletor_id] = chave_publica_pem
    salvar_registro(caminho, registro)


def obter_chave_publica(caminho, coletor_id):
    registro = carregar_registro(caminho)
    if coletor_id not in registro:
        raise KeyError(f"coletor '{coletor_id}' não registrado em {caminho}")
    return serialization.load_pem_public_key(registro[coletor_id].encode())


def registrar_a_partir_de_chave_privada(caminho_registro, caminho_chave_privada, coletor_id):
    chave_privada_bytes = Path(caminho_chave_privada).read_bytes()
    chave_privada = serialization.load_pem_private_key(chave_privada_bytes, password=None)
    chave_publica_pem = chave_privada.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    registrar_coletor(caminho_registro, coletor_id, chave_publica_pem)


def main():
    parser = argparse.ArgumentParser(description='Registro de coletores conhecidos')
    parser.add_argument('--registrar', required=True, help='coletor_id a registrar')
    parser.add_argument('--a-partir-de', required=True, dest='chave_privada', help='caminho da chave privada PEM')
    parser.add_argument('--registro', default='ingestao/coletores_conhecidos.json')
    args = parser.parse_args()
    registrar_a_partir_de_chave_privada(args.registro, args.chave_privada, args.registrar)
    print(f"Coletor {args.registrar} registrado em {args.registro}")


if __name__ == '__main__':
    main()
