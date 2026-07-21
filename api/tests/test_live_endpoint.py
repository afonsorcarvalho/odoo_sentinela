import asyncio
import json
from datetime import datetime

from fastapi.testclient import TestClient

from api import live
from api.main import app
from api.odoo import get_cliente_servico
from api.tests.tenant_fixtures import criar_tenant, remover_tenant

SENSOR_CODE = 'SNR-SIM-TEMP-01'


def _obter_token():
    client = TestClient(app)
    resposta = client.post('/auth/login', json={'usuario': 'admin', 'senha': 'admin'})
    return resposta.json()['access_token']


def test_live_sem_token_retorna_422():
    client = TestClient(app)
    resposta = client.get(f'/sensores/{SENSOR_CODE}/live')
    assert resposta.status_code == 422


def test_live_token_invalido_retorna_401():
    client = TestClient(app)
    resposta = client.get(f'/sensores/{SENSOR_CODE}/live', params={'token': 'lixo.invalido.aqui'})
    assert resposta.status_code == 401


def test_live_sensor_inexistente_retorna_404():
    client = TestClient(app)
    token = _obter_token()
    resposta = client.get('/sensores/SNR-NAO-EXISTE-XYZ/live', params={'token': token})
    assert resposta.status_code == 404


def test_live_recebe_ponto_publicado_no_registry():
    # Nota (desvio do brief): a versão original deste teste usava
    # httpx.ASGITransport + client.stream() sobre a rota HTTP real. Isso
    # trava indefinidamente com qualquer versão atual do httpx (testado
    # 0.27.2 e 0.28.1): ASGITransport só retorna a Response depois que
    # `self.app(scope, receive, send)` termina por completo, ou seja, só
    # depois que o body ASGI fecha com more_body=False — o que nunca
    # acontece para um StreamingResponse infinito como o do SSE aqui.
    # Reproduzido de forma isolada (sem Odoo/DB) para confirmar que é uma
    # limitação da lib, não um bug do endpoint. O teste abaixo chama a
    # coroutine `get_live` diretamente (mesmo caminho de produção:
    # obter_sensor -> registrar -> stream()), o que cobre a mesma lógica
    # sem depender do transporte ASGI. A cobertura HTTP real (200 +
    # publicação via trigger/listener) fica por conta do Step 8
    # (verificação end-to-end com uvicorn de verdade).
    async def cenario():
        cliente = get_cliente_servico()
        resposta = await live.get_live(SENSOR_CODE, cliente=cliente, _claims={})
        agen = resposta.body_iterator
        try:
            live.publicar(SENSOR_CODE, {'sensor_id': SENSOR_CODE, 'site_id': 'SITE-SIM-0001', 'time': 1700000000000, 'valor': 25.0})
            linha = await asyncio.wait_for(agen.__anext__(), timeout=2)
            assert linha.startswith('data: ')
            payload = json.loads(linha[len('data: '):].strip())
            assert payload['valor'] == 25.0
        finally:
            await agen.aclose()

    asyncio.run(cenario())


def test_live_global_sem_token_retorna_422():
    client = TestClient(app)
    resposta = client.get('/live')
    assert resposta.status_code == 422


def test_live_global_token_invalido_retorna_401():
    client = TestClient(app)
    resposta = client.get('/live', params={'token': 'lixo.invalido.aqui'})
    assert resposta.status_code == 401


def test_live_global_recebe_evento_de_qualquer_sensor():
    # Mesma técnica do test_live_recebe_ponto_publicado_no_registry acima: chama a
    # coroutine da rota diretamente (não via ASGI transport), pelo mesmo motivo já
    # documentado (StreamingResponse infinito trava o ASGITransport do httpx).
    async def cenario():
        resposta = await live.get_live_global(cliente=get_cliente_servico(), _claims={})
        agen = resposta.body_iterator
        try:
            live.publicar('QUALQUER-OUTRO-SENSOR', {'sensor_id': 'QUALQUER-OUTRO-SENSOR', 'site_id': 'SITE-SIM-0001', 'time': 1700000000000, 'valor': 15.0})
            linha = await asyncio.wait_for(agen.__anext__(), timeout=2)
            assert linha.startswith('data: ')
            payload = json.loads(linha[len('data: '):].strip())
            assert payload['sensor_id'] == 'QUALQUER-OUTRO-SENSOR'
            assert payload['valor'] == 15.0
        finally:
            await agen.aclose()

    asyncio.run(cenario())


def test_live_sensor_de_outro_tenant_retorna_404():
    ts = datetime.now().isoformat().replace(':', '').replace('.', '')[:15]
    tenant_a = criar_tenant(f'A-{ts}')
    tenant_b = criar_tenant(f'B-{ts}')
    try:
        client = TestClient(app)
        resposta_login = client.post('/auth/login', json={'usuario': tenant_a['login'], 'senha': tenant_a['senha']})
        token = resposta_login.json()['access_token']
        resposta = client.get(f"/sensores/{tenant_b['sensor_code']}/live", params={'token': token})
        assert resposta.status_code == 404
    finally:
        remover_tenant(tenant_a)
        remover_tenant(tenant_b)
