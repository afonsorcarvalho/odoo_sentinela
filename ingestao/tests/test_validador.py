import base64
from datetime import date, datetime

from coletor_simulado import gerador as gerador_simulado
from contrato import formato, identidade as identidade_simulado
from hub.arquivo_diario import ArquivoDiario
from hub.assinador import AssinadorSoftware
from ingestao import registro_coletores, validador


def _gerar_dia_e_registrar(tmp_path, data=date(2026, 7, 18), injetar_alarme=False):
    chave_path = tmp_path / 'chave_coletor.pem'
    output_dir = gerador_simulado.gerar_dia(
        data, tmp_path / 'output', injetar_alarme=injetar_alarme, chave_path=chave_path,
    )
    registro_path = tmp_path / 'registro.json'
    registro_coletores.registrar_a_partir_de_chave_privada(registro_path, chave_path, gerador_simulado.COLETOR_ID)
    return output_dir, registro_path


def test_validar_arquivo_correto(tmp_path):
    output_dir, registro_path = _gerar_dia_e_registrar(tmp_path)
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_leituras_2026-07-18.txt"
    resultado = validador.validar_arquivo(caminho_arquivo, registro_path)
    assert resultado.status_validacao == 'valido'
    assert resultado.total_linhas == 2880
    assert len(resultado.leituras) == 2880
    assert resultado.coletor_id == gerador_simulado.COLETOR_ID
    assert resultado.motivo_rejeicao is None
    assert resultado.data_referencia == '2026-07-18'
    assert resultado.hash_final is not None
    assert resultado.assinatura is not None
    assert resultado.tipo_arquivo == 'leituras'


def test_validar_arquivo_com_linha_corrompida(tmp_path):
    output_dir, registro_path = _gerar_dia_e_registrar(tmp_path)
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_leituras_2026-07-18.txt"
    linhas = caminho_arquivo.read_text().split('\n')
    idx = next(i for i, l in enumerate(linhas) if l and not l.startswith('#'))
    campos = linhas[idx].split('|')
    campos[5] = '999.9'
    linhas[idx] = '|'.join(campos)
    caminho_arquivo.write_text('\n'.join(linhas))

    resultado = validador.validar_arquivo(caminho_arquivo, registro_path)
    assert resultado.status_validacao == 'invalido'
    assert 'quebrada' in resultado.motivo_rejeicao.lower()
    assert resultado.leituras == []
    assert resultado.data_referencia == '2026-07-18'


def test_validar_arquivo_com_chave_errada_registrada(tmp_path):
    output_dir, registro_path = _gerar_dia_e_registrar(tmp_path)
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_leituras_2026-07-18.txt"
    outra_chave_path = tmp_path / 'outra_chave.pem'
    identidade_simulado.carregar_ou_criar_chave(outra_chave_path)
    registro_coletores.registrar_a_partir_de_chave_privada(registro_path, outra_chave_path, gerador_simulado.COLETOR_ID)

    resultado = validador.validar_arquivo(caminho_arquivo, registro_path)
    assert resultado.status_validacao == 'invalido'
    assert 'assinatura' in resultado.motivo_rejeicao.lower()


def test_validar_arquivo_coletor_nao_registrado(tmp_path):
    chave_path = tmp_path / 'chave_coletor.pem'
    output_dir = gerador_simulado.gerar_dia(date(2026, 7, 18), tmp_path / 'output', chave_path=chave_path)
    registro_path = tmp_path / 'registro_vazio.json'
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_leituras_2026-07-18.txt"

    resultado = validador.validar_arquivo(caminho_arquivo, registro_path)
    assert resultado.status_validacao == 'invalido'
    assert 'não registrado' in resultado.motivo_rejeicao


def test_validar_arquivo_alarme_sem_eventos(tmp_path):
    output_dir, registro_path = _gerar_dia_e_registrar(tmp_path, injetar_alarme=False)
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_alarmes_2026-07-18.txt"
    resultado = validador.validar_arquivo(caminho_arquivo, registro_path)
    assert resultado.status_validacao == 'valido'
    assert resultado.tipo_arquivo == 'alarmes'
    assert resultado.total_linhas == 0
    assert resultado.eventos == []


def test_validar_arquivo_alarme_com_par_entrada_saida(tmp_path):
    output_dir, registro_path = _gerar_dia_e_registrar(tmp_path, injetar_alarme=True)
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_alarmes_2026-07-18.txt"
    resultado = validador.validar_arquivo(caminho_arquivo, registro_path)
    assert resultado.status_validacao == 'valido'
    assert resultado.tipo_arquivo == 'alarmes'
    assert len(resultado.eventos) == 2
    assert resultado.eventos[0]['tipo_evento'] == 'entrada_alarme'
    assert resultado.eventos[1]['tipo_evento'] == 'saida_alarme'


def _leitura(ts, valor=96.83):
    return {'timestamp': ts, 'sensor_id': 'SNR-1', 'area_id': 'EXPURGO',
            'tipo_medida': 'temperatura', 'valor': valor, 'unidade': 'C',
            'protocolo_origem': '4-20ma', 'status_leitura': 'ok',
            'cert_ver': 3, 'cal_ganho': 0.965, 'cal_offset': 0.33}


def _preparar(tmp_path, selar=True):
    assinador = AssinadorSoftware(str(tmp_path / "k.pem"))
    arq = ArquivoDiario('COL-1', 'HUB-1', '2.3.1', '-03:00', str(tmp_path / "d"),
                        assinador, cliente_id='CLI-1', site_id='SITE-1')
    arq.registrar(_leitura(datetime(2026, 7, 16, 0, 1, 0)))
    arq.registrar(_leitura(datetime(2026, 7, 16, 0, 2, 0)))
    if selar:
        arq.selar('2026-07-16')
    registro = str(tmp_path / "reg.json")
    registro_coletores.registrar_coletor(registro, 'COL-1', assinador.chave_publica_pem())
    return arq.caminho('2026-07-16'), registro


def test_arquivo_v3_selado_valido(tmp_path):
    caminho, registro = _preparar(tmp_path, selar=True)
    r = validador.validar_arquivo(str(caminho), registro)
    assert r.status_validacao == 'valido'
    assert r.total_linhas == 2
    assert r.cliente_id == 'CLI-1' and r.site_id == 'SITE-1'


def test_arquivo_v2_legado_sem_colunas_ainda_valida(tmp_path):
    # Monta um cabecalho v2 legado A MAO (schema_version 2, sem linha
    # '# colunas:'), fiel ao formato que contrato.formato.montar_cabecalho
    # emitia antes da Task 1 -- nao usa ArquivoDiario/montar_cabecalho atuais,
    # que so emitem v3. Prova que 'colunas' em HEADER_KEYS nao quebra o acervo
    # real de producao (arquivos v2 gerados pelo hub antes deste trabalho).
    assinador = AssinadorSoftware(str(tmp_path / "k.pem"))
    cabecalho = "\n".join([
        "# schema_version: 2",
        "# tipo_arquivo: leituras",
        "# cliente_id: CLI-1",
        "# site_id: SITE-1",
        "# coletor_id: COL-1",
        "# hub_id: HUB-1",
        f"# coletor_pubkey_fingerprint: {assinador.fingerprint()}",
        "# data_referencia: 2026-07-16",
        "# timezone_offset: -03:00",
        "# firmware_version: 2.3.1",
        "# dia_anterior_hash_final: N/A",
    ]) + "\n"

    h = formato.hash_seed(cabecalho)
    hdr_sig = base64.b64encode(assinador.assinar(h.encode())).decode()
    texto = cabecalho + f"# hdr_sig: {hdr_sig}\n"

    linha, h = formato.gerar_linha_leitura(
        h, 1, "2026-07-16T00:01:00", "SNR-1", "EXPURGO", "temperatura",
        96.83, "C", "4-20ma", "ok", 3, 0.965, 0.33,
    )
    sig = base64.b64encode(assinador.assinar(h.encode())).decode()
    texto += linha + "|" + sig + "\n"
    assinatura = base64.b64encode(assinador.assinar(h.encode())).decode()
    texto += formato.montar_rodape(1, h, assinatura, "total_linhas")

    caminho = tmp_path / "v2_legado.txt"
    caminho.write_text(texto)
    registro = str(tmp_path / "reg.json")
    registro_coletores.registrar_coletor(registro, "COL-1", assinador.chave_publica_pem())

    r = validador.validar_arquivo(str(caminho), registro)
    assert r.status_validacao == "valido"
    assert r.total_linhas == 1


def test_valida_arquivo_v3_com_legenda_de_colunas(tmp_path):
    # monta um arquivo assinado v3 de 1 leitura (helper _preparar ja usado
    # acima) e confirma que a linha '# colunas:' esta no cabecalho e nao
    # derruba a validacao — mesmo status do equivalente v2 (test acima).
    caminho, registro = _preparar(tmp_path, selar=True)
    texto = caminho.read_text()
    assert '# schema_version: 3' in texto
    assert '# colunas: seq|timestamp|sensor_id|' in texto

    r = validador.validar_arquivo(str(caminho), registro)
    assert r.status_validacao == 'valido'
    assert r.total_linhas == 2
    assert r.cliente_id == 'CLI-1' and r.site_id == 'SITE-1'


def test_arquivo_sem_rodape_e_incompleto(tmp_path):
    caminho, registro = _preparar(tmp_path, selar=False)  # crash: sem footer
    r = validador.validar_arquivo(str(caminho), registro)
    assert r.status_validacao == 'incompleto'
    assert len(r.leituras) == 2  # aceita linhas verificadas até a última sig válida


def test_sig_de_linha_adulterada_rejeita(tmp_path):
    caminho, registro = _preparar(tmp_path, selar=True)
    linhas = caminho.read_text().split('\n')
    corpo_idx = next(i for i, l in enumerate(linhas) if l and not l.startswith('#'))
    campos = linhas[corpo_idx].split('|')
    campos[5] = '999.99'  # adultera o valor, mantém hash/sig antigos
    linhas[corpo_idx] = '|'.join(campos)
    caminho.write_text('\n'.join(linhas))
    r = validador.validar_arquivo(str(caminho), registro)
    assert r.status_validacao == 'invalido'


def test_hdr_sig_adulterado_rejeita(tmp_path):
    caminho, registro = _preparar(tmp_path, selar=True)
    linhas = caminho.read_text().split('\n')
    i = next(i for i, l in enumerate(linhas) if l.startswith('# cliente_id:'))
    linhas[i] = '# cliente_id: CLI-OUTRO'  # muda header coberto pelo hdr_sig
    caminho.write_text('\n'.join(linhas))
    r = validador.validar_arquivo(str(caminho), registro)
    assert r.status_validacao == 'invalido'
    assert 'header' in (r.motivo_rejeicao or '').lower()


def test_assinatura_footer_corrompida_e_invalido_nao_exception(tmp_path):
    caminho, registro = _preparar(tmp_path, selar=True)
    linhas = caminho.read_text().split('\n')
    i = next(i for i, l in enumerate(linhas) if l.startswith('# assinatura:'))
    linhas[i] = '# assinatura: !!!notbase64!!!'  # base64 malformado, não ausente
    caminho.write_text('\n'.join(linhas))
    r = validador.validar_arquivo(str(caminho), registro)
    assert r.status_validacao == 'invalido'


def test_validar_texto_aceita_chave_publica_resolvida(tmp_path):
    caminho, registro = _preparar(tmp_path, selar=True)
    chave_publica = registro_coletores.obter_chave_publica(registro, 'COL-1')
    texto = caminho.read_text()
    r = validador.validar_texto(texto, chave_publica)
    assert r.status_validacao == 'valido'
    assert r.total_linhas == 2
