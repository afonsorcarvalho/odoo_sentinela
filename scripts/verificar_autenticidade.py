"""CLI de verificação de autenticidade de arquivos de leitura.

Adaptador fino sobre ingestao.verificador: lê arquivo/diretório do disco,
alimenta o núcleo (nome, bytes) e imprime veredito humano ou JSON. Exit codes:
0 todos válidos · 1 ≥1 inválido · 2 ≥1 incompleto · 3 ≥1 indeterminado ·
4 erro de uso. Precedência 4 > 1 > 2 > 3 > 0.
"""
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from ingestao import verificador


def coletar_itens(caminho):
    p = Path(caminho)
    if not p.exists():
        raise FileNotFoundError(f"caminho não encontrado: {caminho}")
    if p.is_file():
        return [(p.name, p.read_bytes())]
    itens = []
    for arq in sorted(p.rglob('*.txt')):
        if arq.is_file():
            itens.append((str(arq.relative_to(p)), arq.read_bytes()))
    return itens


def codigo_saida(lote):
    if lote.invalidos > 0:
        return 1
    if lote.incompletos > 0:
        return 2
    if lote.indeterminados > 0:
        return 3
    return 0


_SIMBOLO = {'valido': 'OK ', 'invalido': 'X  ', 'incompleto': '~  ', 'indeterminado': '?  '}


def _imprimir_humano(lote):
    for i in lote.itens:
        base = f"{_SIMBOLO.get(i.estado, '?  ')} {i.estado.upper():13} {i.nome}"
        detalhe = f"  coletor={i.coletor_id or '-'} data={i.data_referencia or '-'} linhas={i.total_linhas}"
        if i.fingerprint_conferido is not None:
            detalhe += f" fingerprint={'OK' if i.fingerprint_conferido else 'FALHOU'}"
        print(base + detalhe)
        if i.motivo:
            print(f"       motivo: {i.motivo}")
    print(f"\nresumo: {lote.total} arquivo(s) — "
          f"{lote.validos} valido(s), {lote.invalidos} invalido(s), "
          f"{lote.incompletos} incompleto(s), {lote.indeterminados} indeterminado(s)")


def main(argv=None):
    parser = argparse.ArgumentParser(description='Verifica autenticidade de arquivos de leitura assinados')
    parser.add_argument('caminho', help='arquivo .txt assinado ou diretório (walk recursivo)')
    parser.add_argument('--registro', default='ingestao/coletores_conhecidos.json',
                        help='registro de coletores (modo interno)')
    parser.add_argument('--pem', help='chave pública PEM do coletor (modo auditor)')
    parser.add_argument('--json', action='store_true', dest='saida_json', help='saída JSON')
    args = parser.parse_args(argv)

    try:
        itens = coletar_itens(args.caminho)
    except OSError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 4

    pem_bytes = None
    if args.pem:
        try:
            pem_bytes = Path(args.pem).read_bytes()
        except OSError as exc:
            print(f"erro: PEM ilegível: {exc}", file=sys.stderr)
            return 4

    try:
        lote = verificador.verificar_itens(
            itens, registro_path=args.registro, pem_bytes=pem_bytes)
    except ValueError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 4

    if args.saida_json:
        print(json.dumps(asdict(lote), ensure_ascii=False, indent=2))
    else:
        _imprimir_humano(lote)
    return codigo_saida(lote)


if __name__ == '__main__':
    sys.exit(main())
