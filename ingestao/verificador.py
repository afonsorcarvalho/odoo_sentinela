"""Núcleo de verificação de autenticidade, desacoplado da fonte dos bytes.

Recebe uma coleção de (nome, bytes) e devolve um veredito estruturado. Não faz
walk no disco nem sabe o que é zip — isso é dos adaptadores (CLI hoje, endpoint
HTTP amanhã). Reusa a cripto de validador.validar_texto.
"""
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Tuple

from cryptography.hazmat.primitives import serialization

from contrato import identidade
from ingestao import registro_coletores, validador

_MAPA_ESTADO = {'valido': 'valido', 'invalido': 'invalido', 'incompleto': 'incompleto'}


@dataclass
class VerificacaoItem:
    nome: str
    estado: str  # valido | invalido | incompleto | indeterminado
    motivo: Optional[str] = None
    coletor_id: Optional[str] = None
    data_referencia: Optional[str] = None
    total_linhas: int = 0
    hash_final: Optional[str] = None
    fingerprint_conferido: Optional[bool] = None


@dataclass
class VerificacaoLote:
    itens: List[VerificacaoItem] = field(default_factory=list)
    total: int = 0
    validos: int = 0
    invalidos: int = 0
    incompletos: int = 0
    indeterminados: int = 0
    todos_ok: bool = True


def _indeterminado(nome, motivo, coletor_id=None):
    return VerificacaoItem(nome=nome, estado='indeterminado', motivo=motivo, coletor_id=coletor_id)


def _verificar_um(nome, dados, registro_path, chave_pem, fp_pem, chaves_pub):
    try:
        texto = dados.decode('utf-8')
    except UnicodeDecodeError:
        return _indeterminado(nome, 'conteúdo não é texto UTF-8 (não é um arquivo de leitura)')

    metadados_cab = validador.parse_arquivo(texto)[0]
    coletor_id = metadados_cab.get('coletor_id')
    if not coletor_id or not metadados_cab.get('hdr_sig'):
        return _indeterminado(nome, 'não é um arquivo de leitura assinado (header ausente)')

    fingerprint_conferido = None
    if chave_pem is not None:  # modo B
        fp_header = metadados_cab.get('coletor_pubkey_fingerprint')
        if not fp_header:
            return _indeterminado(
                nome, 'header sem coletor_pubkey_fingerprint (não confrontável com a chave fornecida)',
                coletor_id=coletor_id)
        if fp_pem != fp_header:
            return VerificacaoItem(
                nome=nome, estado='invalido', coletor_id=coletor_id,
                data_referencia=metadados_cab.get('data_referencia'),
                fingerprint_conferido=False,
                motivo='chave fornecida não corresponde ao fingerprint declarado no header')
        chave_publica = chave_pem
        fingerprint_conferido = True
    elif chaves_pub is not None:  # modo A — registro em memória (dict do Odoo)
        chave_publica = chaves_pub.get(coletor_id)
        if chave_publica is None:
            return _indeterminado(nome, f"coletor '{coletor_id}' não registrado", coletor_id=coletor_id)
    else:  # modo A — registro em arquivo (retrocompat)
        try:
            chave_publica = registro_coletores.obter_chave_publica(registro_path, coletor_id)
        except KeyError as exc:
            return _indeterminado(nome, str(exc), coletor_id=coletor_id)

    r = validador.validar_texto(texto, chave_publica)
    return VerificacaoItem(
        nome=nome, estado=_MAPA_ESTADO[r.status_validacao], motivo=r.motivo_rejeicao,
        coletor_id=r.coletor_id, data_referencia=r.data_referencia,
        total_linhas=r.total_linhas, hash_final=r.hash_final,
        fingerprint_conferido=fingerprint_conferido)


def verificar_itens(itens: Iterable[Tuple[str, bytes]], *, registro_path=None, pem_bytes=None, chaves_pem=None) -> VerificacaoLote:
    chave_pem = None
    fp_pem = None
    if pem_bytes is not None:
        chave_pem = serialization.load_pem_public_key(pem_bytes)  # ValueError se ilegível
        fp_pem = identidade.fingerprint_de_publica(chave_pem)

    chaves_pub = None
    if chaves_pem is not None:
        chaves_pub = {}
        for cid, pem in chaves_pem.items():
            try:
                chaves_pub[cid] = serialization.load_pem_public_key(pem.encode())
            except (ValueError, TypeError):
                continue  # PEM inválido → coletor não resolvível → indeterminado

    lote = VerificacaoLote()
    for nome, dados in itens:
        item = _verificar_um(nome, dados, registro_path, chave_pem, fp_pem, chaves_pub)
        lote.itens.append(item)
    lote.total = len(lote.itens)
    lote.validos = sum(1 for i in lote.itens if i.estado == 'valido')
    lote.invalidos = sum(1 for i in lote.itens if i.estado == 'invalido')
    lote.incompletos = sum(1 for i in lote.itens if i.estado == 'incompleto')
    lote.indeterminados = sum(1 for i in lote.itens if i.estado == 'indeterminado')
    lote.todos_ok = (lote.total > 0 and lote.invalidos == 0
                     and lote.incompletos == 0 and lote.indeterminados == 0)
    return lote
