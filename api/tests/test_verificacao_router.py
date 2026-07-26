import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import verificacao, verificacao_router as vr


def _app(monkeypatch):
    monkeypatch.setattr(verificacao, 'verificar_upload',
                        lambda nome, dados, chaves_pem=None: verificacao.verificador.VerificacaoLote(total=0))
    vr.reset_estado()  # zera rate-limit + recria gestor
    app = FastAPI()
    app.include_router(vr.router)

    @app.on_event('startup')
    async def _s():
        await vr.gestor.start()

    @app.on_event('shutdown')
    async def _e():
        await vr.gestor.stop()
    return app


def _hdr(**extra):
    h = {'X-Portal-Secret': vr.PORTAL_SECRET}
    h.update(extra)
    return h


def test_post_retorna_job_id_e_get_evolui(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        r = c.post('/verificar', files={'arquivo': ('a.txt', b'x')},
                   headers=_hdr(**{'X-Forwarded-For': '1.1.1.1'}))
        assert r.status_code == 200
        jid = r.json()['job_id']
        # poll
        for _ in range(50):
            s = c.get(f'/verificar/{jid}', headers=_hdr()).json()
            if s['estado'] in ('pronto', 'erro'):
                break
            time.sleep(0.02)
        assert s['estado'] == 'pronto'


def test_get_desconhecido_404(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        assert c.get('/verificar/naoexiste', headers=_hdr()).status_code == 404


def test_rate_limit_por_ip_429(monkeypatch):
    monkeypatch.setattr(vr, 'IP_COTA', 2)
    with TestClient(_app(monkeypatch)) as c:
        h = _hdr(**{'X-Forwarded-For': '9.9.9.9'})
        assert c.post('/verificar', files={'arquivo': ('a.txt', b'x')}, headers=h).status_code == 200
        assert c.post('/verificar', files={'arquivo': ('a.txt', b'x')}, headers=h).status_code == 200
        r = c.post('/verificar', files={'arquivo': ('a.txt', b'x')}, headers=h)
        assert r.status_code == 429 and 'Retry-After' in r.headers


def test_sem_segredo_401(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        r = c.post('/verificar', files={'arquivo': ('a.txt', b'x')})
        assert r.status_code == 401
        r2 = c.get('/verificar/qualquer')
        assert r2.status_code == 401


def test_hits_prune_remove_ips_ociosos(monkeypatch):
    with TestClient(_app(monkeypatch)):
        base = 1000.0
        monkeypatch.setattr(vr, '_now', lambda: base)
        assert vr._rate_ok('1.2.3.4') is True
        assert '1.2.3.4' in vr._hits

        monkeypatch.setattr(vr, '_now', lambda: base + vr.IP_JANELA_S + 1)
        assert vr._rate_ok('5.6.7.8') is True
        assert '1.2.3.4' not in vr._hits
        assert '5.6.7.8' in vr._hits
