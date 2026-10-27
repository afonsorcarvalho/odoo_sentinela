from ingestao import odoo_cliente

TS = "2026-07-26T09:00:00-03:00"
TS_UTC = "2026-07-26 12:00:00"


class FakeOdoo:
    """Fake mínimo de sensor_monitor.alarm.event com search por domínio simples."""

    def __init__(self, registros=None):
        self.registros = {r['id']: dict(r) for r in (registros or [])}
        self.criados = []
        self.escritas = []

    def _casa(self, reg, dominio):
        for campo, op, valor in dominio:
            atual = reg.get(campo, False)
            if op != '=' or atual != valor:
                return False
        return True

    def executar(self, cliente, model, metodo, *args, **kw):
        if metodo == 'search':
            ids = [i for i, r in sorted(self.registros.items()) if self._casa(r, args[0])]
            return ids[:kw['limit']] if kw.get('limit') else ids
        if metodo == 'read':
            return [dict(self.registros[i]) for i in args[0]]
        if metodo == 'create':
            novo = max(self.registros, default=0) + 1
            self.registros[novo] = {'id': novo, 'timestamp_resolucao_sensor': False, **args[0]}
            self.criados.append(args[0])
            return novo
        if metodo == 'write':
            for i in args[0]:
                self.registros[i].update(args[1])
            self.escritas.append((args[0], args[1]))
            return True
        raise AssertionError(metodo)


def _evento(tipo_evento='entrada_alarme', ts=TS):
    return {'timestamp': ts, 'tipo_evento': tipo_evento, 'tipo_violacao': 'falha_sensor',
            'valor': 0.0, 'limite_min_vigente': None, 'limite_max_vigente': None}


def _reg(**kw):
    base = {'id': 5, 'sensor_id': 1, 'timestamp_deteccao': TS_UTC,
            'timestamp_resolucao_sensor': False, 'origem_arquivo_hash': False}
    base.update(kw)
    return base


def test_entrada_mesmo_evento_aberto_devolve_e_grava_hash(monkeypatch):
    fake = FakeOdoo([_reg()])
    monkeypatch.setattr(odoo_cliente, 'executar', fake.executar)
    assert odoo_cliente.processar_entrada_alarme(None, _evento(), 1, 2, 3, 'HASH') == 5
    assert fake.criados == []
    assert fake.registros[5]['origem_arquivo_hash'] == 'HASH'


def test_entrada_mesmo_evento_fechado_nao_duplica(monkeypatch):
    fake = FakeOdoo([_reg(timestamp_resolucao_sensor='2026-07-26 12:05:00')])
    monkeypatch.setattr(odoo_cliente, 'executar', fake.executar)
    assert odoo_cliente.processar_entrada_alarme(None, _evento(), 1, 2, 3, 'HASH') == 5
    assert fake.criados == []
    assert fake.registros[5]['origem_arquivo_hash'] == 'HASH'


def test_entrada_nao_sobrescreve_hash_existente(monkeypatch):
    fake = FakeOdoo([_reg(origem_arquivo_hash='ANTIGO')])
    monkeypatch.setattr(odoo_cliente, 'executar', fake.executar)
    assert odoo_cliente.processar_entrada_alarme(None, _evento(), 1, 2, 3, 'NOVO') == 5
    assert fake.registros[5]['origem_arquivo_hash'] == 'ANTIGO'


def test_entrada_ao_vivo_sem_hash_cria_sem_hash(monkeypatch):
    fake = FakeOdoo()
    monkeypatch.setattr(odoo_cliente, 'executar', fake.executar)
    novo = odoo_cliente.processar_entrada_alarme(None, _evento(), 1, 2, 3, None)
    assert fake.registros[novo]['origem_arquivo_hash'] is False
    assert fake.registros[novo]['timestamp_deteccao'] == TS_UTC


def test_entrada_outro_timestamp_com_aberto_devolve_aberto(monkeypatch):
    fake = FakeOdoo([_reg()])
    monkeypatch.setattr(odoo_cliente, 'executar', fake.executar)
    ev = _evento(ts="2026-07-26T09:10:00-03:00")
    assert odoo_cliente.processar_entrada_alarme(None, ev, 1, 2, 3, 'H') == 5
    assert fake.criados == []


def test_saida_ja_fechada_pelo_ao_vivo_nao_e_orfa(monkeypatch):
    fake = FakeOdoo([_reg(timestamp_resolucao_sensor='2026-07-26 12:05:00')])
    monkeypatch.setattr(odoo_cliente, 'executar', fake.executar)
    ev = _evento('saida_alarme', ts="2026-07-26T09:05:00-03:00")
    assert odoo_cliente.processar_saida_alarme(None, ev, 1) == 5


def test_sequencia_ao_vivo_entrada_saida_depois_arquivo_um_registro(monkeypatch):
    fake = FakeOdoo()
    monkeypatch.setattr(odoo_cliente, 'executar', fake.executar)
    sai = _evento('saida_alarme', ts="2026-07-26T09:05:00-03:00")
    a = odoo_cliente.processar_entrada_alarme(None, _evento(), 1, 2, 3, None)
    assert odoo_cliente.processar_saida_alarme(None, sai, 1) == a
    # arquivo chega depois
    assert odoo_cliente.processar_entrada_alarme(None, _evento(), 1, 2, 3, 'H') == a
    assert odoo_cliente.processar_saida_alarme(None, sai, 1) == a
    assert len(fake.registros) == 1
    assert fake.registros[a]['origem_arquivo_hash'] == 'H'
    assert fake.registros[a]['timestamp_resolucao_sensor'] == '2026-07-26 12:05:00'


def test_ao_vivo_aberto_sem_hash_arquivo_com_timestamp_diferente(monkeypatch):
    """Comportamento atual documentado: entrada do arquivo com timestamp diferente,
    havendo alarme aberto ao vivo (sem hash) no sensor → devolve o aberto, não cria
    e não carimba hash (não é o mesmo evento)."""
    fake = FakeOdoo([_reg()])
    monkeypatch.setattr(odoo_cliente, 'executar', fake.executar)
    ev = _evento(ts="2026-07-26T09:00:30-03:00")
    assert odoo_cliente.processar_entrada_alarme(None, ev, 1, 2, 3, 'H') == 5
    assert fake.criados == []
    assert fake.registros[5]['origem_arquivo_hash'] is False
