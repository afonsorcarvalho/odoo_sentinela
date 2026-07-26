from ingestao import odoo_cliente


def test_entrada_nao_duplica_evento_aberto(monkeypatch):
    chamadas = []

    def fake_executar(cliente, model, metodo, *args, **kw):
        chamadas.append((model, metodo))
        if model == 'sensor_monitor.alarm.event' and metodo == 'search':
            return [55]                       # já existe aberto
        if metodo == 'create':
            raise AssertionError("não deveria criar quando já há aberto")
        return []

    monkeypatch.setattr(odoo_cliente, 'executar', fake_executar)
    evento = {'tipo_violacao': 'acima_limite', 'timestamp': '2026-07-26T12:00:00-03:00',
              'valor': 30.0, 'limite_min_vigente': 18.0, 'limite_max_vigente': 25.0}
    res = odoo_cliente.processar_entrada_alarme(None, evento, 70, 50, 20, 'HASH')
    assert res == 55


def test_entrada_cria_quando_nao_ha_aberto(monkeypatch):
    def fake_executar(cliente, model, metodo, *args, **kw):
        if model == 'sensor_monitor.alarm.event' and metodo == 'search':
            return []
        if metodo == 'create':
            return 99
        return []
    monkeypatch.setattr(odoo_cliente, 'executar', fake_executar)
    evento = {'tipo_violacao': 'acima_limite', 'timestamp': '2026-07-26T12:00:00-03:00',
              'valor': 30.0, 'limite_min_vigente': 18.0, 'limite_max_vigente': 25.0}
    assert odoo_cliente.processar_entrada_alarme(None, evento, 70, 50, 20, 'HASH') == 99
