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


def test_post_retorna_job_id_e_get_evolui(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        r = c.post('/verificar', files={'arquivo': ('a.txt', b'x')},
                   headers={'X-Forwarded-For': '1.1.1.1'})
        assert r.status_code == 200
        jid = r.json()['job_id']
        # poll
        for _ in range(50):
            s = c.get(f'/verificar/{jid}').json()
            if s['estado'] in ('pronto', 'erro'):
                break
            time.sleep(0.02)
        assert s['estado'] == 'pronto'


def test_get_desconhecido_404(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        assert c.get('/verificar/naoexiste').status_code == 404


def test_rate_limit_por_ip_429(monkeypatch):
    monkeypatch.setattr(vr, 'IP_COTA', 2)
    with TestClient(_app(monkeypatch)) as c:
        h = {'X-Forwarded-For': '9.9.9.9'}
        assert c.post('/verificar', files={'arquivo': ('a.txt', b'x')}, headers=h).status_code == 200
        assert c.post('/verificar', files={'arquivo': ('a.txt', b'x')}, headers=h).status_code == 200
        r = c.post('/verificar', files={'arquivo': ('a.txt', b'x')}, headers=h)
        assert r.status_code == 429 and 'Retry-After' in r.headers
