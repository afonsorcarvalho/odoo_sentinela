from datetime import date

from coletor_simulado import gerador as gerador_simulado
from ingestao import ingestor, registro_coletores, timescale

DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'


def _limpar(site_id):
    conn = timescale.conectar(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sensor_reading WHERE site_id = %s", (site_id,))
        conn.commit()
    finally:
        conn.close()


def test_ingerir_arquivo_valido_grava_no_timescale(tmp_path):
    site_id = 'SITE-TEST-INGESTOR-OK'
    chave_path = tmp_path / 'chave.pem'
    output_dir = gerador_simulado.gerar_dia(date(2026, 7, 19), tmp_path / 'output', chave_path=chave_path)
    registro_path = tmp_path / 'registro.json'
    registro_coletores.registrar_a_partir_de_chave_privada(registro_path, chave_path, gerador_simulado.COLETOR_ID)
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_leituras_2026-07-19.txt"

    _limpar(site_id)
    try:
        resultado = ingestor.ingerir_arquivo(caminho_arquivo, registro_path, DSN, site_id)
        assert resultado.status_validacao == 'valido'
        assert resultado.total_linhas == 2880
        assert resultado.total_gravado == 2880
    finally:
        _limpar(site_id)


def test_ingerir_arquivo_corrompido_nao_grava_nada(tmp_path):
    site_id = 'SITE-TEST-INGESTOR-BAD'
    chave_path = tmp_path / 'chave.pem'
    output_dir = gerador_simulado.gerar_dia(date(2026, 7, 20), tmp_path / 'output', chave_path=chave_path)
    registro_path = tmp_path / 'registro.json'
    registro_coletores.registrar_a_partir_de_chave_privada(registro_path, chave_path, gerador_simulado.COLETOR_ID)
    caminho_arquivo = output_dir / f"{gerador_simulado.COLETOR_ID}_leituras_2026-07-20.txt"
    linhas = caminho_arquivo.read_text().split('\n')
    campos = linhas[9].split('|')
    campos[5] = '999.9'
    linhas[9] = '|'.join(campos)
    caminho_arquivo.write_text('\n'.join(linhas))

    _limpar(site_id)
    try:
        resultado = ingestor.ingerir_arquivo(caminho_arquivo, registro_path, DSN, site_id)
        assert resultado.status_validacao == 'invalido'
        assert resultado.total_gravado == 0
        with_conn = timescale.conectar(DSN)
        try:
            with with_conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM sensor_reading WHERE site_id = %s", (site_id,))
                (total,) = cur.fetchone()
            assert total == 0
        finally:
            with_conn.close()
    finally:
        _limpar(site_id)
