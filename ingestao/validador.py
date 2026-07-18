import base64
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from . import registro_coletores


@dataclass
class ResultadoValidacao:
    status_validacao: str
    motivo_rejeicao: str
    total_linhas: int
    coletor_id: str
    leituras: list = field(default_factory=list)


def _parse_bloco_metadados(linhas):
    metadados = {}
    for linha in linhas:
        if not linha.startswith('#'):
            continue
        chave, _, valor = linha[2:].partition(':')
        metadados[chave.strip()] = valor.strip()
    return metadados


def parse_arquivo(texto):
    linhas = texto.split('\n')
    if linhas and linhas[-1] == '':
        linhas = linhas[:-1]
    idx = 0
    linhas_cabecalho = []
    while idx < len(linhas) and linhas[idx].startswith('#'):
        linhas_cabecalho.append(linhas[idx])
        idx += 1
    linhas_corpo = []
    while idx < len(linhas) and not linhas[idx].startswith('#'):
        linhas_corpo.append(linhas[idx])
        idx += 1
    linhas_rodape = linhas[idx:]
    cabecalho_canonico = '\n'.join(linhas_cabecalho) + '\n'
    metadados_cabecalho = _parse_bloco_metadados(linhas_cabecalho)
    metadados_rodape = _parse_bloco_metadados(linhas_rodape)
    return metadados_cabecalho, cabecalho_canonico, linhas_corpo, metadados_rodape


def parse_linha_leitura(linha):
    campos = linha.split('|')
    (seq, timestamp, sensor_id, area_id, tipo_medida, valor, unidade,
     protocolo_origem, status_leitura, hash_linha) = campos
    linha_sem_hash = '|'.join(campos[:-1])
    return {
        'seq': int(seq),
        'timestamp': timestamp,
        'sensor_id': sensor_id,
        'area_id': area_id,
        'tipo_medida': tipo_medida,
        'valor': float(valor),
        'unidade': unidade,
        'protocolo_origem': protocolo_origem,
        'status_leitura': status_leitura,
        'hash': hash_linha,
        'linha_sem_hash': linha_sem_hash,
    }


def _hash_seed(cabecalho_canonico):
    return hashlib.sha256(cabecalho_canonico.encode()).hexdigest()


def _hash_linha(hash_anterior, linha_sem_hash):
    return hashlib.sha256((hash_anterior + linha_sem_hash).encode()).hexdigest()


def validar_arquivo(caminho, registro_path):
    texto = Path(caminho).read_text()
    metadados_cab, cabecalho_canonico, linhas_corpo, metadados_rod = parse_arquivo(texto)
    coletor_id = metadados_cab.get('coletor_id')
    total_linhas = len(linhas_corpo)

    hash_atual = _hash_seed(cabecalho_canonico)
    leituras = []
    for linha in linhas_corpo:
        parsed = parse_linha_leitura(linha)
        hash_esperado = _hash_linha(hash_atual, parsed['linha_sem_hash'])
        if hash_esperado != parsed['hash']:
            return ResultadoValidacao(
                status_validacao='invalido',
                motivo_rejeicao=f"cadeia de hash quebrada na linha seq={parsed['seq']}",
                total_linhas=total_linhas,
                coletor_id=coletor_id,
            )
        hash_atual = hash_esperado
        leituras.append(parsed)

    hash_final_declarado = metadados_rod.get('hash_final')
    if hash_atual != hash_final_declarado:
        return ResultadoValidacao(
            status_validacao='invalido',
            motivo_rejeicao='hash_final do rodapé não bate com a cadeia recalculada',
            total_linhas=total_linhas,
            coletor_id=coletor_id,
        )

    try:
        chave_publica = registro_coletores.obter_chave_publica(registro_path, coletor_id)
    except KeyError as exc:
        return ResultadoValidacao(
            status_validacao='invalido',
            motivo_rejeicao=str(exc),
            total_linhas=total_linhas,
            coletor_id=coletor_id,
        )

    assinatura = base64.b64decode(metadados_rod.get('assinatura'))
    try:
        chave_publica.verify(assinatura, hash_final_declarado.encode(), ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return ResultadoValidacao(
            status_validacao='invalido',
            motivo_rejeicao='assinatura inválida',
            total_linhas=total_linhas,
            coletor_id=coletor_id,
        )

    return ResultadoValidacao(
        status_validacao='valido',
        motivo_rejeicao=None,
        total_linhas=total_linhas,
        coletor_id=coletor_id,
        leituras=leituras,
    )
