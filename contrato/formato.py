import hashlib

CARACTERES_PROIBIDOS = ('|', '\n', '\r')


def validar_identificador(valor):
    if any(c in valor for c in CARACTERES_PROIBIDOS):
        raise ValueError(f"identificador '{valor}' contém caractere proibido (|, \\n ou \\r)")


def validar_segmento_path(valor):
    if valor in ('', '.', '..') or '/' in valor or '\\' in valor:
        raise ValueError(f"segmento de path inválido: '{valor}'")


def montar_cabecalho(tipo_arquivo, coletor_id, hub_id, pubkey_fingerprint,
                     data_referencia, timezone_offset, firmware_version,
                     cliente_id, site_id):
    for valor in (coletor_id, hub_id, cliente_id, site_id):
        validar_identificador(valor)
    linhas = [
        "# schema_version: 2",
        f"# tipo_arquivo: {tipo_arquivo}",
        f"# cliente_id: {cliente_id}",
        f"# site_id: {site_id}",
        f"# coletor_id: {coletor_id}",
        f"# hub_id: {hub_id}",
        f"# coletor_pubkey_fingerprint: {pubkey_fingerprint}",
        f"# data_referencia: {data_referencia}",
        f"# timezone_offset: {timezone_offset}",
        f"# firmware_version: {firmware_version}",
    ]
    if tipo_arquivo == 'leituras':
        linhas.append("# dia_anterior_hash_final: N/A")
    return '\n'.join(linhas) + '\n'


def hash_seed(cabecalho_canonico):
    return hashlib.sha256(cabecalho_canonico.encode()).hexdigest()


def hash_linha(hash_anterior, linha_sem_hash):
    return hashlib.sha256((hash_anterior + linha_sem_hash).encode()).hexdigest()


def fmt_coef(valor):
    return f"{float(valor):.4f}"


def gerar_linha_leitura(hash_anterior, seq, timestamp, sensor_id, area_id, tipo_medida,
                        valor, unidade, protocolo_origem, status_leitura,
                        cert_ver, cal_ganho, cal_offset):
    for identificador in (sensor_id, area_id):
        validar_identificador(identificador)
    campos_sem_hash = [
        str(seq), timestamp, sensor_id, area_id, tipo_medida, str(valor), unidade,
        protocolo_origem, status_leitura,
        str(int(cert_ver)), fmt_coef(cal_ganho), fmt_coef(cal_offset),
    ]
    linha_sem_hash = '|'.join(campos_sem_hash)
    novo_hash = hash_linha(hash_anterior, linha_sem_hash)
    return linha_sem_hash + '|' + novo_hash, novo_hash


def gerar_linha_alarme(hash_anterior, seq, timestamp, sensor_id, area_id, tipo_medida, tipo_evento, tipo_violacao, valor, limite_min_vigente, limite_max_vigente):
    for identificador in (sensor_id, area_id):
        validar_identificador(identificador)

    def fmt_limite(v):
        return '—' if v is None else str(v)

    campos_sem_hash = [
        str(seq), timestamp, sensor_id, area_id, tipo_medida, tipo_evento, tipo_violacao,
        str(valor), fmt_limite(limite_min_vigente), fmt_limite(limite_max_vigente),
    ]
    linha_sem_hash = '|'.join(campos_sem_hash)
    novo_hash = hash_linha(hash_anterior, linha_sem_hash)
    return linha_sem_hash + '|' + novo_hash, novo_hash


def montar_rodape(total, hash_final, assinatura_b64, campo_total):
    return (
        f"# {campo_total}: {total}\n"
        f"# hash_final: {hash_final}\n"
        f"# assinatura: {assinatura_b64}\n"
    )
