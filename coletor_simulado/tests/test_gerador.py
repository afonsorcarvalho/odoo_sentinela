import base64
from datetime import date

from coletor_simulado import gerador
from contrato import formato, identidade


def test_gerar_dia_sem_alarme(tmp_path):
    chave_path = tmp_path / 'chave.pem'
    output_dir = gerador.gerar_dia(date(2026, 7, 18), tmp_path / 'output', injetar_alarme=False, chave_path=chave_path)
    leituras = (output_dir / 'COL-SIM-0001_leituras_2026-07-18.txt').read_text()
    alarmes = (output_dir / 'COL-SIM-0001_alarmes_2026-07-18.txt').read_text()
    assert '# total_linhas: 2880' in leituras
    assert '# total_eventos: 0' in alarmes
    assert '# tipo_arquivo: leituras' in leituras
    assert '# tipo_arquivo: alarmes' in alarmes


def test_gerar_dia_com_alarme_injeta_par_entrada_saida(tmp_path):
    chave_path = tmp_path / 'chave.pem'
    output_dir = gerador.gerar_dia(date(2026, 7, 18), tmp_path / 'output', injetar_alarme=True, chave_path=chave_path)
    alarmes = (output_dir / 'COL-SIM-0001_alarmes_2026-07-18.txt').read_text()
    assert '# total_eventos: 2' in alarmes

    # Verify timestamps are on the same lines as event types (no transposition)
    linhas = alarmes.strip().split('\n')
    corpo_linhas = [l for l in linhas if l and not l.startswith('#')]

    entrada_line = next((l for l in corpo_linhas if 'entrada_alarme' in l), None)
    saida_line = next((l for l in corpo_linhas if 'saida_alarme' in l), None)

    assert entrada_line is not None, "entrada_alarme not found"
    assert saida_line is not None, "saida_alarme not found"
    assert 'T02:00:00' in entrada_line, "T02:00:00 should be on entrada_alarme line"
    assert 'T02:07:00' in saida_line, "T02:07:00 should be on saida_alarme line"


def test_assinatura_do_rodape_de_leituras_verifica(tmp_path):
    chave_path = tmp_path / 'chave.pem'
    output_dir = gerador.gerar_dia(date(2026, 7, 18), tmp_path / 'output', chave_path=chave_path)
    chave = identidade.carregar_ou_criar_chave(chave_path)
    conteudo = (output_dir / 'COL-SIM-0001_leituras_2026-07-18.txt').read_text()
    linhas = conteudo.strip().split('\n')
    hash_final = next(l for l in linhas if l.startswith('# hash_final:')).split(': ', 1)[1]
    assinatura_b64 = next(l for l in linhas if l.startswith('# assinatura:')).split(': ', 1)[1]
    assinatura = base64.b64decode(assinatura_b64)
    identidade.verificar_assinatura(chave.public_key(), assinatura, hash_final.encode())


def test_assinatura_do_rodape_de_alarmes_verifica(tmp_path):
    chave_path = tmp_path / 'chave.pem'
    output_dir = gerador.gerar_dia(date(2026, 7, 18), tmp_path / 'output', injetar_alarme=False, chave_path=chave_path)
    chave = identidade.carregar_ou_criar_chave(chave_path)
    conteudo = (output_dir / 'COL-SIM-0001_alarmes_2026-07-18.txt').read_text()
    linhas = conteudo.strip().split('\n')
    hash_final = next(l for l in linhas if l.startswith('# hash_final:')).split(': ', 1)[1]
    assinatura_b64 = next(l for l in linhas if l.startswith('# assinatura:')).split(': ', 1)[1]
    assinatura = base64.b64decode(assinatura_b64)
    identidade.verificar_assinatura(chave.public_key(), assinatura, hash_final.encode())


def test_hdr_sig_presente_e_valido(tmp_path):
    chave_path = tmp_path / 'chave.pem'
    output_dir = gerador.gerar_dia(date(2026, 7, 18), tmp_path / 'output', chave_path=chave_path)
    chave = identidade.carregar_ou_criar_chave(chave_path)
    conteudo = (output_dir / 'COL-SIM-0001_leituras_2026-07-18.txt').read_text()
    linhas = conteudo.split('\n')
    linhas_header = []
    for l in linhas:
        if not l.startswith('#'):
            break
        linhas_header.append(l)
    cabecalho_canonico = '\n'.join(
        l for l in linhas_header if not l.startswith('# hdr_sig:')
    ) + '\n'
    hdr_sig_b64 = next(l for l in linhas_header if l.startswith('# hdr_sig:')).split(': ', 1)[1]
    hash_0 = formato.hash_seed(cabecalho_canonico)
    identidade.verificar_assinatura(chave.public_key(), base64.b64decode(hdr_sig_b64), hash_0.encode())


def test_sig_da_ultima_linha_de_leituras_verifica(tmp_path):
    chave_path = tmp_path / 'chave.pem'
    output_dir = gerador.gerar_dia(date(2026, 7, 18), tmp_path / 'output', chave_path=chave_path)
    chave = identidade.carregar_ou_criar_chave(chave_path)
    conteudo = (output_dir / 'COL-SIM-0001_leituras_2026-07-18.txt').read_text()
    linhas = conteudo.strip().split('\n')
    corpo_linhas = [l for l in linhas if l and not l.startswith('#')]
    ultima_linha = corpo_linhas[-1]
    campos = ultima_linha.split('|')
    assert len(campos) == 14  # 12 colunas de dado + hash + sig
    hash_da_linha = campos[-2]
    sig_b64 = campos[-1]
    identidade.verificar_assinatura(chave.public_key(), base64.b64decode(sig_b64), hash_da_linha.encode())


def test_chave_persiste_entre_execucoes(tmp_path):
    chave_path = tmp_path / 'chave.pem'
    gerador.gerar_dia(date(2026, 7, 18), tmp_path / 'output1', chave_path=chave_path)
    gerador.gerar_dia(date(2026, 7, 19), tmp_path / 'output2', chave_path=chave_path)
    conteudo1 = (tmp_path / 'output1' / 'COL-SIM-0001_leituras_2026-07-18.txt').read_text()
    conteudo2 = (tmp_path / 'output2' / 'COL-SIM-0001_leituras_2026-07-19.txt').read_text()
    fingerprint1 = next(l for l in conteudo1.split('\n') if 'pubkey_fingerprint' in l)
    fingerprint2 = next(l for l in conteudo2.split('\n') if 'pubkey_fingerprint' in l)
    assert fingerprint1 == fingerprint2
