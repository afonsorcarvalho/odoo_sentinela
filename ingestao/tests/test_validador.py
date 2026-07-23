from datetime import date, datetime

from coletor_simulado import gerador as gerador_simulado
from contrato import identidade as identidade_simulado
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


def test_arquivo_v2_selado_valido(tmp_path):
    caminho, registro = _preparar(tmp_path, selar=True)
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
