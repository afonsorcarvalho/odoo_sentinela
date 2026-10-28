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
            {'sensor_code': 'SNR-A', 'nome': 'Câmara fria <1>', 'unidade': '°C', 'site': 'Hospital Central',
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
    assert 'mín 2,00 / máx 8,00 °C' in t
    assert 'sem limite cadastrado' in t
    assert 'Limite alterado em 10/01/2026 08:00 (de 7,00 para 8,00)' in t
    assert 'Sem dados' in t and 'Falha do instrumento' in t
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
