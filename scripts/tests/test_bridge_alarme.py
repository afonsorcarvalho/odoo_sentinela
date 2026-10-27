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
    monkeypatch.setattr(bridge, '_alarme_no_odoo', lambda *a: None)
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


_PAYLOAD_ENTRADA = {"timestamp": "2026-07-26T12:00:00+00:00", "sensor_id": "SNR-T-01",
                    "area_id": "AREA-T", "tipo_medida": "temperatura",
                    "tipo_evento": "entrada_alarme", "tipo_violacao": "falha_sensor",
                    "valor": 0.0, "limite_min": None, "limite_max": None}


def _prepara_odoo(monkeypatch):
    monkeypatch.setattr(bridge, '_site_code', lambda coletor_id: 'SITE-T')
    monkeypatch.setattr(bridge, '_ids_odoo', lambda coletor, sensor: (11, 22, 33))
    monkeypatch.setattr(bridge, '_obter_cliente_odoo', lambda: 'CLI')


def test_entrada_alarme_abre_no_odoo_ao_vivo_e_notifica(monkeypatch):
    _prepara_odoo(monkeypatch)
    chamadas = []
    monkeypatch.setattr(bridge.odoo_cliente, 'processar_entrada_alarme',
                        lambda *a, **k: chamadas.append((a, k)) or 99)
    conn = _Conn()
    bridge._on_message(conn)(None, None, _msg("sentinela/alarme/HUB-T/COL-T/SNR-T-01",
                                              _PAYLOAD_ENTRADA))
    assert len(chamadas) == 1
    a, k = chamadas[0]
    cliente, evento, sensor, area, coletor = a[:5]
    hash_arquivo = a[5] if len(a) > 5 else k.get('hash_arquivo')
    assert (cliente, sensor, area, coletor) == ('CLI', 11, 22, 33)
    assert hash_arquivo is None
    assert evento['timestamp'] == _PAYLOAD_ENTRADA['timestamp']
    assert evento['tipo_violacao'] == 'falha_sensor'
    assert evento['limite_min_vigente'] is None and evento['limite_max_vigente'] is None
    assert len(conn.notifies) == 1


def test_saida_alarme_fecha_no_odoo(monkeypatch):
    _prepara_odoo(monkeypatch)
    chamadas = []
    monkeypatch.setattr(bridge.odoo_cliente, 'processar_saida_alarme',
                        lambda *a, **k: chamadas.append(a) or 99)
    conn = _Conn()
    bridge._on_message(conn)(None, None, _msg("sentinela/alarme/HUB-T/COL-T/SNR-T-01",
                                              {**_PAYLOAD_ENTRADA, "tipo_evento": "saida_alarme"}))
    assert chamadas and chamadas[0][0] == 'CLI' and chamadas[0][2] == 11
    assert len(conn.notifies) == 1


def test_falha_odoo_nao_impede_notify(monkeypatch):
    _prepara_odoo(monkeypatch)
    invalidou = []
    monkeypatch.setattr(bridge, '_invalidar_cliente_odoo', lambda: invalidou.append(1))

    def boom(*a, **k):
        raise ConnectionRefusedError("odoo fora")
    monkeypatch.setattr(bridge.odoo_cliente, 'processar_entrada_alarme', boom)
    conn = _Conn()
    bridge._on_message(conn)(None, None, _msg("sentinela/alarme/HUB-T/COL-T/SNR-T-01",
                                              _PAYLOAD_ENTRADA))
    assert len(conn.notifies) == 1 and conn.committed
    assert invalidou == [1]


def test_cliente_odoo_preguicoso_e_reconecta(monkeypatch):
    conexoes = []
    monkeypatch.setattr(bridge.odoo_cliente, 'conectar',
                        lambda *a: conexoes.append(a) or f'C{len(conexoes)}')
    monkeypatch.setattr(bridge, '_cliente_odoo', None)
    assert bridge._obter_cliente_odoo() == 'C1'
    assert bridge._obter_cliente_odoo() == 'C1'
    bridge._invalidar_cliente_odoo()
    assert bridge._obter_cliente_odoo() == 'C2'


def _odoo_falso(monkeypatch, sensores):
    """sensores: lista de dicts {sensor_code, coletor_id, id, area_id}."""
    monkeypatch.setattr(bridge, '_site_code', lambda coletor_id: 'SITE-T')
    monkeypatch.setattr(bridge, '_obter_cliente_odoo', lambda: 'CLI')
    monkeypatch.setattr(bridge, '_coletor_odoo_id', {})
    monkeypatch.setattr(bridge, '_sensor_odoo', {})
    monkeypatch.setattr(bridge.odoo_cliente, 'resolver_coletor',
                        lambda cli, code: {'id': {'COL-T': 33, 'COL-X': 44}[code]})

    def fake_executar(cli, model, metodo, dominio, **kw):
        assert model == 'sensor_monitor.sensor' and metodo == 'search_read'
        filtro = dict((c, v) for c, _, v in dominio)
        return [{'id': s['id'], 'area_id': [s['area_id'], 'A']} for s in sensores
                if s['sensor_code'] == filtro['sensor_code']
                and s['coletor_id'] == filtro.get('coletor_id', s['coletor_id'])]
    monkeypatch.setattr(bridge.odoo_cliente, 'executar', fake_executar)


def test_sensor_de_outro_coletor_nao_toca_odoo_mas_notifica(monkeypatch):
    # SNR-T-01 pertence ao COL-X (outro site); tópico forjado usa COL-T.
    _odoo_falso(monkeypatch, [{'sensor_code': 'SNR-T-01', 'coletor_id': 44, 'id': 11, 'area_id': 22}])
    chamadas = []
    monkeypatch.setattr(bridge.odoo_cliente, 'processar_entrada_alarme',
                        lambda *a, **k: chamadas.append(a))
    monkeypatch.setattr(bridge.odoo_cliente, 'processar_saida_alarme',
                        lambda *a, **k: chamadas.append(a))
    conn = _Conn()
    h = bridge._on_message(conn)
    h(None, None, _msg("sentinela/alarme/HUB-T/COL-T/SNR-T-01", _PAYLOAD_ENTRADA))
    h(None, None, _msg("sentinela/alarme/HUB-T/COL-T/SNR-T-01",
                       {**_PAYLOAD_ENTRADA, "tipo_evento": "saida_alarme"}))
    assert chamadas == []
    assert len(conn.notifies) == 2


def test_sensor_do_proprio_coletor_resolve(monkeypatch):
    _odoo_falso(monkeypatch, [{'sensor_code': 'SNR-T-01', 'coletor_id': 33, 'id': 11, 'area_id': 22}])
    assert bridge._ids_odoo('COL-T', 'SNR-T-01') == (11, 22, 33)
