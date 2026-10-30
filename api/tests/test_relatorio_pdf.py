import re

from fastapi.testclient import TestClient

from api.main import app
from api.relatorio_pdf import gerar_pdf, rotulo_bucket, slug

client = TestClient(app)
DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'
SENSOR_CODE = 'SNR-SIM-TEMP-01'
DIA = '2026-01-10'


def _texto(pdf: bytes) -> str:
    """Texto dos operadores Tj de um PDF sem compressao (cp1252 + escapes octais)."""
    out = []
    for lit in re.findall(rb'\(((?:\\.|[^\\)])*)\)\s*Tj', pdf):
        lit = re.sub(rb'\\([0-7]{3})', lambda m: bytes([int(m.group(1), 8)]), lit)
        out.append(lit.replace(b'\\(', b'(').replace(b'\\)', b')').replace(b'\\\\', b'\\').decode('cp1252'))
    return '\n'.join(out)


def _bucket(hora, avg=None, mn=None, mx=None, n_ok=0, n_falha=0, estado='sem_dados', fora=False):
    return {'bucket': f'2026-01-10T{hora:02d}:00:00-03:00', 'avg': avg, 'min': mn, 'max': mx,
            'n_ok': n_ok, 'n_falha': n_falha, 'estado': estado, 'fora_limite': fora}


def _relatorio():
    buckets1 = [_bucket(h) for h in range(24)]
    buckets1[10] = _bucket(10, 5.0, 4.5, 5.5, 6, 0, 'ok')
    buckets1[11] = _bucket(11, 6.0, 5.0, 9.5, 6, 1, 'ok', True)
    buckets1[14] = _bucket(14, None, None, None, 0, 4, 'falha_instrumento')
    buckets1[15] = _bucket(15, 7.0, 6.5, 7.5, 6, 0, 'ok')
    buckets2 = [_bucket(h) for h in range(24)]
    return {
        'inicio': DIA, 'fim': DIA, 'granularidade': 'hora', 'fuso': 'America/Sao_Paulo',
        'emitido_em': '2026-01-11T12:30:00+00:00', 'emissor': 'Maria (maria@x.com)',
        'sensores': [
            {'sensor_code': 'SNR-A', 'nome': 'Câmara fria <1>', 'unidade': '°C', 'site': 'Hospital Central', 'area': 'CME (Preparo)',
             'localizacao': 'Câmara 1 — saída do exaustor', 'endereco': 'Rua A, 10',
             'limites': {'limite_min': 2.0, 'limite_max': 8.0},
             'alteracoes_limite': [{'quando': '2026-01-10T11:00:00+00:00', 'campo': 'limite_max', 'de': 7.0, 'para': 8.0}],
             'buckets': buckets1,
             'alarmes': [{'id': 1, 'sensor_code': 'SNR-A', 'area_code': 'A', 'timestamp_deteccao': 1768053600000,
                          'timestamp_resolucao_sensor': 1768057200000, 'valor_lido': 9.5,
                          'tipo_violacao': 'acima_limite', 'limite_configurado_snapshot': 8.0, 'status': 'resolvido',
                          'usuario_responsavel': None, 'data_resolucao': None, 'observacoes': None}]},
            {'sensor_code': 'SNR-B', 'nome': 'Sala 2', 'unidade': '%', 'site': None, 'limites': None,
             'alteracoes_limite': [], 'buckets': buckets2, 'alarmes': []},
        ],
    }


def test_pdf_conteudo():
    pdf = gerar_pdf(_relatorio(), 'Hospital São José', compress=False)
    assert pdf.startswith(b'%PDF')
    t = _texto(pdf)
    assert 'Hospital São José' in t
    assert '10/01/2026 – 10/01/2026' in t
    assert 'Por hora' in t and 'America/Sao_Paulo' in t
    assert 'Maria (maria@x.com)' in t and '11/01/2026 09:30' in t  # emitido em local
    assert 'Câmara fria' in t and '(SNR-A)' in t
    assert 'CME (Preparo)' in t and 'Câmara 1 — saída do exaustor' in t and 'Rua A, 10' in t
    assert 'não informada' in t  # SNR-B sem localização
    assert 'mín 2,00 / máx 8,00 °C' in t
    assert 'sem limite cadastrado' in t
    assert 'Limite alterado em 10/01/2026 08:00 (de 7,00 para 8,00)' in t
    assert 'Sem dados' in t and 'Falha de instrumento' in t
    assert '9,50' in t and '10:00' in t
    assert 'Acima do limite' in t and 'Resolvido' in t
    assert 'Nenhum alarme no período.' in t
    total = int(re.search(r'Página 1 de (\d+)', t).group(1))
    assert total >= 2 and f'Página {total} de {total}' in t


def test_pdf_comprimido_valido():
    assert gerar_pdf(_relatorio(), 'X').startswith(b'%PDF')


def test_pdf_muitos_buckets_pagina_mais_de_uma():
    rel = _relatorio()
    rel['granularidade'] = 'dia'
    rel['sensores'][0]['buckets'] = [
        {'bucket': f'2026-01-{d:02d}T00:00:00-03:00', 'avg': 5.0, 'min': 4.0, 'max': 6.0,
         'n_ok': 10, 'n_falha': 0, 'estado': 'ok', 'fora_limite': False} for d in range(1, 32)]
    t = _texto(gerar_pdf(rel, 'X', compress=False))
    assert '31/01/2026' in t and 'Página 1 de' in t


def test_rotulos():
    assert rotulo_bucket('2026-01-10T07:00:00-03:00', 'hora') == '07:00'
    assert rotulo_bucket('2026-01-10T00:00:00-03:00', 'dia') == '10/01/2026'
    assert rotulo_bucket('2026-10-01T00:00:00-03:00', 'mes') == 'out/2026'


def test_slug():
    assert slug('Hospital São José Ltda.') == 'hospital-sao-jose-ltda'
    assert slug('') == 'cliente'


def test_rota_pdf():
    token = client.post('/auth/login', json={'usuario': 'admin', 'senha': 'admin'}).json()['access_token']
    resp = client.get('/relatorio.pdf', params={'sensores': SENSOR_CODE, 'inicio': DIA, 'fim': DIA},
                      headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    assert resp.headers['content-type'] == 'application/pdf'
    assert re.fullmatch(r'attachment; filename="relatorio_[a-z0-9-]+_2026-01-10_2026-01-10\.pdf"',
                        resp.headers['content-disposition'])
    assert resp.content.startswith(b'%PDF')


def test_rota_pdf_erros():
    token = client.post('/auth/login', json={'usuario': 'admin', 'senha': 'admin'}).json()['access_token']
    h = {'Authorization': f'Bearer {token}'}
    assert client.get('/relatorio.pdf', params={'sensores': SENSOR_CODE, 'inicio': DIA, 'fim': '2026-01-09'},
                      headers=h).status_code == 422
    assert client.get('/relatorio.pdf', params={'sensores': 'SNR-NAO-EXISTE-XYZ', 'inicio': DIA, 'fim': DIA},
                      headers=h).status_code == 404
    assert client.get('/relatorio.pdf', params={'sensores': SENSOR_CODE, 'inicio': DIA, 'fim': DIA}).status_code == 401


def test_pdf_alarme_sem_timestamp_nao_quebra():
    rel = _relatorio()
    rel['sensores'][0]['alarmes'][0]['timestamp_deteccao'] = None
    t = _texto(gerar_pdf(rel, 'X', compress=False))
    assert 'Acima do limite' in t and '—' in t


def test_pdf_heading_alarmes_keep_with_next():
    from api.relatorio_pdf import _estilos
    assert _estilos()['h3'].keepWithNext


def test_pdf_alteracao_limite_apos_periodo():
    rel = _relatorio()
    rel['sensores'][0]['alteracoes_limite'].append(
        {'quando': '2026-01-12T15:00:00+00:00', 'campo': 'limite_min', 'de': 2.0, 'para': 3.0})
    t = _texto(gerar_pdf(rel, 'X', compress=False))
    assert 'Limite alterado em 12/01/2026 12:00 (de 2,00 para 3,00) — limite mínimo — após o período' in t
    # alteracao dentro do periodo nao recebe o sufixo
    assert 'Limite alterado em 10/01/2026 08:00 (de 7,00 para 8,00) — limite máximo' in t
    assert '(de 7,00 para 8,00) — limite máximo — após' not in t


def _rel_mes(inicio, fim, meses):
    rel = _relatorio()
    rel.update({'inicio': inicio, 'fim': fim, 'granularidade': 'mes'})
    rel['sensores'] = rel['sensores'][:1]
    rel['sensores'][0]['alteracoes_limite'] = []
    rel['sensores'][0]['buckets'] = [
        {'bucket': f'{m}-01T00:00:00-03:00', 'avg': 5.0, 'min': 4.0, 'max': 6.0, 'n_ok': 9, 'n_falha': 0,
         'estado': 'ok', 'fora_limite': False} for m in meses]
    return rel


def test_pdf_mes_parcial_notas():
    t = _texto(gerar_pdf(_rel_mes('2026-01-15', '2026-03-10', ['2026-01', '2026-02', '2026-03']), 'X', compress=False))
    assert 'Primeiro mês parcial: dados de 15/01/2026 a 31/01/2026.' in t
    assert 'Último mês parcial: dados de 01/03/2026 a 10/03/2026.' in t


def test_pdf_mes_completo_sem_nota():
    t = _texto(gerar_pdf(_rel_mes('2026-01-01', '2026-02-28', ['2026-01', '2026-02']), 'X', compress=False))
    assert 'mês parcial' not in t


def test_pdf_mes_unico_parcial():
    t = _texto(gerar_pdf(_rel_mes('2026-01-05', '2026-01-20', ['2026-01']), 'X', compress=False))
    assert 'Mês parcial: dados de 05/01/2026 a 20/01/2026.' in t



def _png_bytes():
    import base64
    # PNG 2x1 vermelho, gerado offline.
    return base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAIAAAB7QOjdAAAAEElEQVR4nGP4z8DAwMDAAAAHBAEAXp0n5wAAAABJRU5ErkJggg==')


def test_pdf_com_logo_embute_imagem():
    pdf = gerar_pdf(_relatorio(), 'X', compress=False, logo=_png_bytes())
    assert b'/Subtype /Image' in pdf


def test_pdf_sem_logo_sem_imagem():
    pdf = gerar_pdf(_relatorio(), 'X', compress=False)
    assert b'/Subtype /Image' not in pdf


def test_pdf_logo_invalido_nao_quebra():
    pdf = gerar_pdf(_relatorio(), 'X', compress=False, logo=b'nao e imagem')
    assert pdf.startswith(b'%PDF')
    assert b'/Subtype /Image' not in pdf


def test_num_casas_e_zero_pad():
    from api.relatorio_pdf import _num
    assert _num(9.5) == '9,50'
    assert _num(9.5, 1, 3) == '009,5'
    assert _num(1234.5, 0, 2) == '1234'  # padding nunca corta
    assert _num(-2.25, 1, 2) == '-02,2'
    assert _num(-0.001, 2) == '0,00'
    assert _num(None, 3, 4) == '—'


def test_pdf_respeita_formato_do_sensor():
    r = _relatorio()
    r['sensores'][0]['formato'] = {'casas_decimais': 1, 'digitos_inteiros': 3}
    t = _texto(gerar_pdf(r, 'X', compress=False))
    assert '009,5' in t and 'mín 002,0 / máx 008,0' in t
    assert '9,50' not in t.split('Sala 2')[0]


def test_pdf_grafico_resumo_max_min():
    t = _texto(gerar_pdf(_relatorio(), 'X', compress=False))
    assert 'Máximo no período:' in t and 'Mínimo:' in t
    assert 'Laranja' in t and 'máximo' in t
