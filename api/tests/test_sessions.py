import time

from api import sessions


def test_guardar_e_obter_retorna_cliente():
    sessions.guardar('jti-1', 'cliente-fake', exp=int(time.time()) + 60)
    assert sessions.obter('jti-1') == 'cliente-fake'
    sessions.remover('jti-1')


def test_obter_jti_inexistente_retorna_none():
    assert sessions.obter('jti-nao-existe') is None


def test_obter_sessao_expirada_retorna_none_e_remove():
    sessions.guardar('jti-expirado', 'cliente-fake', exp=int(time.time()) - 1)
    assert sessions.obter('jti-expirado') is None
    assert sessions.obter('jti-expirado') is None


def test_remover_apaga_sessao():
    sessions.guardar('jti-2', 'cliente-fake', exp=int(time.time()) + 60)
    sessions.remover('jti-2')
    assert sessions.obter('jti-2') is None
