import json
from types import SimpleNamespace

import scripts.bridge_telemetria as bridge


class _Cursor:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self._conn.notifies.append((sql, params))


class _Conn:
    def __init__(self):
        self.notifies = []
        self.inseridos = []
        self.committed = False

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.committed = True


def _msg(topic, payload):
    return SimpleNamespace(topic=topic, payload=json.dumps(payload).encode())


def test_alarme_vira_pg_notify_sem_inserir(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(bridge, '_site_code', lambda coletor_id: 'SITE-T')
    inseriu = []
    monkeypatch.setattr(bridge.timescale, 'inserir_leituras',
                        lambda *a, **k: inseriu.append(a))

    handler = bridge._on_message(conn)
    payload = {"timestamp": "2026-07-26T12:00:00+00:00", "sensor_id": "SNR-T-01",
               "area_id": "AREA-T", "tipo_medida": "temperatura",
               "tipo_evento": "entrada_alarme", "tipo_violacao": "acima_limite",
               "valor": 30.0, "limite_min": 18.0, "limite_max": 25.0}
    handler(None, None, _msg("sentinela/alarme/HUB-T/COL-T/SNR-T-01", payload))

    assert inseriu == []                       # não insere leitura
    assert len(conn.notifies) == 1
    sql, params = conn.notifies[0]
    assert 'pg_notify' in sql and 'alarme_ao_vivo' in (sql + str(params))
    assert conn.committed is True
    enviado = json.loads(params[0] if params else sql.split("'")[-2])
    assert enviado["tipo"] == "alarme_ao_vivo"
    assert enviado["sensor_id"] == "SNR-T-01"
    assert enviado["site_id"] == "SITE-T"
    assert enviado["valor"] == 30.0


def test_telemetria_continua_inserindo(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(bridge, '_site_code', lambda coletor_id: 'SITE-T')
    inseriu = []
    monkeypatch.setattr(bridge.timescale, 'inserir_leituras',
                        lambda *a, **k: inseriu.append(a))
    handler = bridge._on_message(conn)
    handler(None, None, _msg("sentinela/telemetria/HUB-T/COL-T/SNR-T-01",
            {"timestamp": "2026-07-26T12:00:00+00:00", "valor": 20.0}))
    assert len(inseriu) == 1
    assert conn.notifies == []                 # telemetria não emite alarme
