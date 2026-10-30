from datetime import datetime, timezone

from fastapi.testclient import TestClient

from api import relatorio as rel
from api.main import app
from api.tests.tenant_fixtures import criar_tenant, remover_tenant
from ingestao.timescale import conectar

client = TestClient(app)
DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'
SENSOR_CODE = 'SNR-SIM-TEMP-01'
SITE = 'SITE-SIM-0001'
DIA = '2026-01-10'


def _headers():
    token = client.post('/auth/login', json={'usuario': 'admin', 'senha': 'admin'}).json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def _limpar():
    conn = conectar(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sensor_reading WHERE sensor_id = %s", (SENSOR_CODE,))
        conn.commit()
    finally:
        conn.close()


def _inserir(leituras):
    conn = conectar(DSN)
    try:
        with conn.cursor() as cur:
            for ts, valor in leituras:
                cur.execute(
                    "INSERT INTO sensor_reading "
                    "(time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (ts, SITE, 'COL-SIM-0001', SENSOR_CODE, 'AREA-SIM-EXPURGO', 'temperatura', valor, 'C', '4-20ma', 'ok'),
                )
        conn.commit()
    finally:
        conn.close()


def _get(sensores, inicio=DIA, fim=DIA, headers=None):
    return client.get('/relatorio', params={'sensores': sensores, 'inicio': inicio, 'fim': fim},
                      headers=headers if headers is not None else _headers())


def test_relatorio_formato_e_fora_limite(monkeypatch):
    monkeypatch.setattr(rel, 'obter_threshold', lambda c, code: {
        'sensor_id': code, 'limite_min': 2.0, 'limite_max': 8.0, 'is_valor_padrao_regulatorio': False})
    _limpar()
    try:
        # 10:00 local = 13:00 UTC (UTC-3); 12:00 local = 15:00 UTC
        _inserir([(datetime(2026, 1, 10, 13, 10, tzinfo=timezone.utc), 5.0),
                  (datetime(2026, 1, 10, 15, 10, tzinfo=timezone.utc), 9.5)])
        resp = _get(SENSOR_CODE)
        assert resp.status_code == 200
        corpo = resp.json()
        assert corpo['inicio'] == DIA and corpo['fim'] == DIA
        assert corpo['granularidade'] == 'hora'
        assert corpo['fuso'] == 'America/Sao_Paulo'
        assert corpo['emissor'] and datetime.fromisoformat(corpo['emitido_em'])
        s = corpo['sensores'][0]
        assert s['sensor_code'] == SENSOR_CODE
        assert s['nome'] and s['unidade'] and s['site'] and s['area']
        assert 'localizacao' in s and 'endereco' in s
        assert s['limites'] == {'limite_min': 2.0, 'limite_max': 8.0}
        assert isinstance(s['alteracoes_limite'], list) and isinstance(s['alarmes'], list)
        assert len(s['buckets']) == 24
        por_hora = {b['bucket']: b for b in s['buckets']}
        b10 = por_hora['2026-01-10T10:00:00-03:00']
        assert b10['avg'] == 5.0 and b10['estado'] == 'ok' and b10['fora_limite'] is False
        b12 = por_hora['2026-01-10T12:00:00-03:00']
        assert b12['max'] == 9.5 and b12['fora_limite'] is True
        vazio = por_hora['2026-01-10T00:00:00-03:00']
        assert vazio['estado'] == 'sem_dados' and vazio['avg'] is None and vazio['fora_limite'] is False
    finally:
        _limpar()


def test_relatorio_sem_threshold_limites_none(monkeypatch):
    monkeypatch.setattr(rel, 'obter_threshold', lambda c, code: None)
    _limpar()
    try:
        _inserir([(datetime(2026, 1, 10, 13, 10, tzinfo=timezone.utc), 999.0)])
        s = _get(SENSOR_CODE).json()['sensores'][0]
        assert s['limites'] is None
        assert all(b['fora_limite'] is False for b in s['buckets'])
    finally:
        _limpar()


def test_relatorio_granularidade_dia():
    resp = _get(SENSOR_CODE, inicio='2026-01-01', fim='2026-01-31')
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo['granularidade'] == 'dia' and len(corpo['sensores'][0]['buckets']) == 31


def test_relatorio_422_sensores_demais():
    codigos = ','.join(f'SNR-X-{i}' for i in range(21))
    assert _get(codigos).status_code == 422


def test_relatorio_422_periodo_longo():
    assert _get(SENSOR_CODE, inicio='2025-01-01', fim='2026-01-02').status_code == 422  # 367 dias


def test_relatorio_366_dias_aceito():
    assert _get(SENSOR_CODE, inicio='2025-01-01', fim='2025-12-31').status_code == 200


def test_relatorio_422_fim_antes_inicio():
    assert _get(SENSOR_CODE, inicio='2026-01-10', fim='2026-01-09').status_code == 422


def test_relatorio_404_sensor_inexistente():
    assert _get('SNR-NAO-EXISTE-XYZ').status_code == 404
    assert _get(f'{SENSOR_CODE},SNR-NAO-EXISTE-XYZ').status_code == 404


def test_relatorio_404_sensor_de_outro_tenant():
    tenant_a = criar_tenant('REL-A')
    tenant_b = criar_tenant('REL-B')
    try:
        # login do tenant A na API: usa as credenciais do usuario criado
        token = client.post('/auth/login', json={'usuario': tenant_a['login'], 'senha': tenant_a['senha']}).json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        assert _get(tenant_b['sensor_code'], headers=headers).status_code == 404
        assert _get(tenant_a['sensor_code'], headers=headers).status_code == 200
    finally:
        remover_tenant(tenant_a)
        remover_tenant(tenant_b)


def test_relatorio_sem_auth_retorna_401():
    resp = client.get('/relatorio', params={'sensores': SENSOR_CODE, 'inicio': DIA, 'fim': DIA})
    assert resp.status_code == 401
