from unittest import mock

from api import verificacao_chaves as vc


def test_chaves_do_odoo_monta_dict_e_cacheia(monkeypatch):
    vc.invalidar_cache()
    chamadas = {'n': 0}

    def fake_executar(cliente, model, method, *args, **kwargs):
        chamadas['n'] += 1
        return [
            {'coletor_code': 'COL-1', 'pubkey_pem': 'PEM1'},
            {'coletor_code': 'COL-2', 'pubkey_pem': 'PEM2'},
            {'coletor_code': 'COL-3', 'pubkey_pem': False},  # sem PEM -> fora
        ]

    monkeypatch.setattr(vc, 'get_cliente_servico', lambda: object())
    monkeypatch.setattr(vc.odoo_cliente, 'executar', fake_executar)

    d1 = vc.chaves_do_odoo()
    assert d1 == {'COL-1': 'PEM1', 'COL-2': 'PEM2'}
    d2 = vc.chaves_do_odoo()          # dentro do TTL -> cache
    assert d2 == d1
    assert chamadas['n'] == 1         # só uma ida ao Odoo

    d3 = vc.chaves_do_odoo(force=True)  # força refresh
    assert chamadas['n'] == 2
    assert d3 == d1
