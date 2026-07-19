from datetime import date

from coletor_simulado import gerador as gerador_simulado
from coletor_simulado import identidade as identidade_simulado
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
    campos = linhas[9].split('|')
    campos[5] = '999.9'
    linhas[9] = '|'.join(campos)
    caminho_arquivo.write_text('\n'.join(linhas))

    resultado = validador.validar_arquivo(caminho_arquivo, registro_path)
    assert resultado.status_validacao == 'invalido'
    assert 'hash' in resultado.motivo_rejeicao.lower()
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
