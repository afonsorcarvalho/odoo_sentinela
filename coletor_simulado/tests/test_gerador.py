import base64
from datetime import date

from coletor_simulado import gerador, identidade


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
    assert 'entrada_alarme' in alarmes
    assert 'saida_alarme' in alarmes
    assert 'T02:00:00' in alarmes
    assert 'T02:07:00' in alarmes


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


def test_chave_persiste_entre_execucoes(tmp_path):
    chave_path = tmp_path / 'chave.pem'
    gerador.gerar_dia(date(2026, 7, 18), tmp_path / 'output1', chave_path=chave_path)
    gerador.gerar_dia(date(2026, 7, 19), tmp_path / 'output2', chave_path=chave_path)
    conteudo1 = (tmp_path / 'output1' / 'COL-SIM-0001_leituras_2026-07-18.txt').read_text()
    conteudo2 = (tmp_path / 'output2' / 'COL-SIM-0001_leituras_2026-07-19.txt').read_text()
    fingerprint1 = next(l for l in conteudo1.split('\n') if 'pubkey_fingerprint' in l)
    fingerprint2 = next(l for l in conteudo2.split('\n') if 'pubkey_fingerprint' in l)
    assert fingerprint1 == fingerprint2
