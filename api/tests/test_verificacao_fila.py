import asyncio

from api import verificacao


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_enfileira_e_processa(monkeypatch):
    monkeypatch.setattr(verificacao, 'verificar_upload',
                        lambda nome, dados, chaves_pem=None: f'LOTE:{nome}')
    g = verificacao.Gestor()
    _run(g.start())
    try:
        job = g.enfileirar('a.txt', b'x')
        assert job.estado in ('fila', 'processando')
        _run(_espera_pronto(g, job.id))
        assert g.obter(job.id).estado == 'pronto'
        assert g.obter(job.id).lote == 'LOTE:a.txt'
    finally:
        _run(g.stop())


async def _espera_pronto(g, job_id, timeout=2.0):
    import time
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        if g.obter(job_id) and g.obter(job_id).estado in ('pronto', 'erro'):
            return
        await asyncio.sleep(0.02)
    raise AssertionError('job não ficou pronto')


def test_fila_cheia(monkeypatch):
    monkeypatch.setattr(verificacao, 'FILA_MAX', 0)
    g = verificacao.Gestor()
    import pytest
    with pytest.raises(verificacao.FilaCheia):
        g.enfileirar('a.txt', b'x')


def test_job_expira(monkeypatch):
    relogio = {'t': 1000.0}
    monkeypatch.setattr(verificacao, 'TTL_RESULTADO_S', 10)
    g = verificacao.Gestor(agora=lambda: relogio['t'])
    job = g.enfileirar('a.txt', b'x')
    job.estado = 'pronto'; job.lote = 'X'; job.expira_em = relogio['t'] + 10
    assert g.obter(job.id) is not None
    relogio['t'] += 11
    g.varrer_expirados()
    assert g.obter(job.id) is None


def test_obter_expira_lazy_sem_sweep_explicito():
    relogio = {'t': 1000.0}
    g = verificacao.Gestor(agora=lambda: relogio['t'])
    job = g.enfileirar('a.txt', b'x')
    job.estado = 'pronto'; job.lote = 'X'; job.expira_em = relogio['t'] + 10
    assert g.obter(job.id) is not None
    relogio['t'] += 11
    assert g.obter(job.id) is None


def test_enfileirar_varre_expirados():
    relogio = {'t': 1000.0}
    g = verificacao.Gestor(agora=lambda: relogio['t'])
    job_a = g.enfileirar('a.txt', b'x')
    job_a.estado = 'pronto'; job_a.lote = 'A'; job_a.expira_em = relogio['t'] + 10
    relogio['t'] += 11
    g.enfileirar('b.txt', b'x')
    # verifica o store diretamente (sem passar por obter, que também expira
    # lazy) para isolar o sweep feito por enfileirar em si
    assert job_a.id not in g._jobs


def test_start_idempotente():
    g = verificacao.Gestor()
    _run(g.start())
    try:
        tarefas1 = list(g._tarefas)
        _run(g.start())
        assert g._tarefas == tarefas1  # mesmas tasks: não respawnou um 2º lote
    finally:
        _run(g.stop())
