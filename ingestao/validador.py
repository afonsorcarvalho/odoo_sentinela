import base64
import binascii
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from contrato import formato
from . import registro_coletores

HEADER_KEYS = {
    'schema_version', 'tipo_arquivo', 'cliente_id', 'site_id', 'coletor_id', 'hub_id',
    'coletor_pubkey_fingerprint', 'data_referencia', 'timezone_offset',
    'firmware_version', 'dia_anterior_hash_final', 'hdr_sig',
}


@dataclass
class ResultadoValidacao:
    status_validacao: str
    motivo_rejeicao: str
    total_linhas: int
    coletor_id: str
    data_referencia: str = None
    hash_final: str = None
    assinatura: str = None
    tipo_arquivo: str = None
    cliente_id: str = None
    site_id: str = None
    pubkey_fingerprint: str = None
    timezone_offset: str = None
    leituras: list = field(default_factory=list)
    eventos: list = field(default_factory=list)


def _parse_bloco_metadados(linhas):
    metadados = {}
    for linha in linhas:
        if not linha.startswith('#'):
            continue
        chave, _, valor = linha[2:].partition(':')
        metadados[chave.strip()] = valor.strip()
    return metadados


def _eh_linha_cabecalho(linha):
    if not linha.startswith('#'):
        return False
    chave, _, _ = linha[2:].partition(':')
    return chave.strip() in HEADER_KEYS


def parse_arquivo(texto):
    linhas = texto.split('\n')
    if linhas and linhas[-1] == '':
        linhas = linhas[:-1]
    idx = 0
    linhas_cabecalho = []
    while idx < len(linhas) and _eh_linha_cabecalho(linhas[idx]):
        linhas_cabecalho.append(linhas[idx])
        idx += 1
    linhas_corpo = []
    while idx < len(linhas) and not linhas[idx].startswith('#'):
        linhas_corpo.append(linhas[idx])
        idx += 1
    linhas_rodape = linhas[idx:]
    # canônico do header = tudo menos a linha hdr_sig (que assina esse canônico)
    canonico = [l for l in linhas_cabecalho if not l.startswith('# hdr_sig:')]
    cabecalho_canonico = '\n'.join(canonico) + '\n'
    metadados_cabecalho = _parse_bloco_metadados(linhas_cabecalho)
    metadados_rodape = _parse_bloco_metadados(linhas_rodape)
    return metadados_cabecalho, cabecalho_canonico, linhas_corpo, metadados_rodape


def parse_linha_leitura(linha):
    campos = linha.split('|')
    (seq, timestamp, sensor_id, area_id, tipo_medida, valor, unidade,
     protocolo_origem, status_leitura, cert_ver, cal_ganho, cal_offset,
     hash_linha, sig) = campos
    return {
        'seq': int(seq), 'timestamp': timestamp, 'sensor_id': sensor_id,
        'area_id': area_id, 'tipo_medida': tipo_medida, 'valor': float(valor),
        'unidade': unidade, 'protocolo_origem': protocolo_origem,
        'status_leitura': status_leitura, 'cert_ver': int(cert_ver),
        'cal_ganho': float(cal_ganho), 'cal_offset': float(cal_offset),
        'hash': hash_linha, 'sig': sig, 'linha_sem_hash': '|'.join(campos[:-2]),
    }


def parse_linha_alarme(linha):
    campos = linha.split('|')
    (seq, timestamp, sensor_id, area_id, tipo_medida, tipo_evento, tipo_violacao,
     valor, limite_min_vigente, limite_max_vigente, hash_linha, sig) = campos
    return {
        'seq': int(seq), 'timestamp': timestamp, 'sensor_id': sensor_id,
        'area_id': area_id, 'tipo_medida': tipo_medida, 'tipo_evento': tipo_evento,
        'tipo_violacao': tipo_violacao, 'valor': float(valor),
        'limite_min_vigente': None if limite_min_vigente == '—' else float(limite_min_vigente),
        'limite_max_vigente': None if limite_max_vigente == '—' else float(limite_max_vigente),
        'hash': hash_linha, 'sig': sig, 'linha_sem_hash': '|'.join(campos[:-2]),
    }


def _verificar_sig(chave_publica, sig_b64, hash_hex):
    try:
        assinatura = base64.b64decode(sig_b64)
    except (binascii.Error, TypeError, ValueError) as exc:
        raise InvalidSignature('assinatura base64 inválida ou ausente') from exc
    chave_publica.verify(assinatura, hash_hex.encode(), ec.ECDSA(hashes.SHA256()))


def validar_arquivo(caminho, registro_path):
    texto = Path(caminho).read_text()
    metadados_cab, cabecalho_canonico, linhas_corpo, metadados_rod = parse_arquivo(texto)
    coletor_id = metadados_cab.get('coletor_id')
    tipo_arquivo = metadados_cab.get('tipo_arquivo')
    hash_final_declarado = metadados_rod.get('hash_final')
    assinatura_declarada = metadados_rod.get('assinatura')

    def _res(status, motivo, leituras=None, total=None):
        r = ResultadoValidacao(
            status_validacao=status, motivo_rejeicao=motivo,
            total_linhas=total if total is not None else len(linhas_corpo),
            coletor_id=coletor_id, data_referencia=metadados_cab.get('data_referencia'),
            hash_final=hash_final_declarado, assinatura=assinatura_declarada,
            tipo_arquivo=tipo_arquivo, cliente_id=metadados_cab.get('cliente_id'),
            site_id=metadados_cab.get('site_id'),
            pubkey_fingerprint=metadados_cab.get('coletor_pubkey_fingerprint'),
            timezone_offset=metadados_cab.get('timezone_offset'))
        if leituras is not None:
            if tipo_arquivo == 'alarmes':
                r.eventos = leituras
            else:
                r.leituras = leituras
        return r

    try:
        chave_publica = registro_coletores.obter_chave_publica(registro_path, coletor_id)
    except KeyError as exc:
        return _res('invalido', str(exc))

    # 1. hdr_sig semeia a cadeia
    hash_atual = formato.hash_seed(cabecalho_canonico)
    hdr_sig = metadados_cab.get('hdr_sig')
    if not hdr_sig:
        return _res('invalido', 'header sem hdr_sig (schema v2 exige header assinado)')
    try:
        _verificar_sig(chave_publica, hdr_sig, hash_atual)
    except InvalidSignature:
        return _res('invalido', 'assinatura do header (hdr_sig) inválida')

    # 2. caminha a cadeia, verificando hash + sig por linha
    parse_linha = parse_linha_alarme if tipo_arquivo == 'alarmes' else parse_linha_leitura
    validas = []
    for linha in linhas_corpo:
        try:
            parsed = parse_linha(linha)
        except ValueError:
            break  # linha malformada (cauda truncada por crash)
        hash_esperado = formato.hash_linha(hash_atual, parsed['linha_sem_hash'])
        if hash_esperado != parsed['hash']:
            break
        try:
            _verificar_sig(chave_publica, parsed['sig'], parsed['hash'])
        except InvalidSignature:
            break
        hash_atual = hash_esperado
        validas.append(parsed)

    tem_footer = hash_final_declarado is not None
    quebrou_cedo = len(validas) < len(linhas_corpo)

    # 3. decidir status
    if tem_footer:
        if quebrou_cedo:
            return _res('invalido',
                        f'cadeia/sig quebrada na linha seq={len(validas) + 1}', total=len(linhas_corpo))
        if hash_atual != hash_final_declarado:
            return _res('invalido', 'hash_final do rodapé não bate com a cadeia recalculada')
        try:
            _verificar_sig(chave_publica, assinatura_declarada, hash_final_declarado)
        except InvalidSignature:
            return _res('invalido', 'assinatura do arquivo (footer) inválida')
        return _res('valido', None, leituras=validas, total=len(validas))

    # sem footer: autêntico até a última sig válida, porém não fechado
    return _res('incompleto', 'arquivo sem rodapé (crash não-recuperado)',
                leituras=validas, total=len(validas))
