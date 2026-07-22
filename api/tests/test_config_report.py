import json
import os
import time

import paho.mqtt.client as mqtt
from fastapi.testclient import TestClient

from api.main import app
from api.odoo import get_cliente_servico
from ingestao import odoo_cliente

MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))


def test_applied_fecha_drift_no_odoo():
    cliente = get_cliente_servico()
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)
    site = ex('sensor_monitor.site', 'search', [('site_code', '=', 'SITE-RPT-01')]) or [
        ex('sensor_monitor.site', 'create', {
            'name': 'S', 'partner_id': ex('res.partner', 'search', [], limit=1)[0],
            'site_code': 'SITE-RPT-01', 'vertical': 'cme_hospitalar'})]
    hub = ex('sensor_monitor.hub', 'search', [('hub_code', '=', 'HUB-RPT-01')]) or [
        ex('sensor_monitor.hub', 'create', {'name': 'H', 'site_id': site[0], 'hub_code': 'HUB-RPT-01'})]
    ex('sensor_monitor.hub', 'write', [hub[0]], {'config_version_desejada': 8, 'config_version_aplicada': 0,
                                                   'config_version_reportada_em': False})

    # Starlette 0.49.x só dispara os eventos de startup do FastAPI dentro do
    # context manager (`__enter__` chama `wait_startup`) — sem o `with`, o
    # OUVINTE_REPORT nunca assina o tópico (mesmo gotcha do Task 8, ver
    # api/tests/test_presenca.py). Além disso, ao contrário do Task 8, a
    # mensagem aqui NÃO é retida (sem retain=True no publish do brief), então
    # a assinatura precisa existir ANTES do publish — não dá pra publicar
    # fora do `with` como no teste de presença.
    with TestClient(app) as client:
        time.sleep(1.0)  # deixa o OUVINTE_REPORT (startup) assinar antes do publish

        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        c.connect(MQTT_HOST, MQTT_PORT, 30)
        c.publish('sentinela/config/applied/hub/HUB-RPT-01',
                  json.dumps({'version': 8, 'aplicado_em': '2026-07-22T10:00:00+00:00', 'status': 'ok'}),
                  qos=1)
        c.disconnect()

        fim = time.time() + 6
        aplicada = 0
        while time.time() < fim:
            aplicada = ex('sensor_monitor.hub', 'read', [hub[0]], fields=['config_version_aplicada'])[0]['config_version_aplicada']
            if aplicada == 8:
                break
            time.sleep(0.3)
        assert aplicada == 8

        # confirma que o write do datetime (config_version_reportada_em) não
        # falhou silenciosamente por causa do formato ISO com timezone — o
        # write de aplicada+reportada_em é atômico (mesma chamada), então se
        # o datetime tivesse quebrado o XML-RPC, aplicada nunca teria chegado
        # a 8; este assert extra deixa explícito que o campo foi de fato
        # populado.
        reportada = ex('sensor_monitor.hub', 'read', [hub[0]], fields=['config_version_reportada_em'])[0]['config_version_reportada_em']
        assert reportada


def test_applied_status_erro_nao_grava_versao():
    # Cobre a guarda explícita do brief ("status:'erro' não grava a
    # versão") — o teste feliz acima não prova esse branch.
    cliente = get_cliente_servico()
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)
    site = ex('sensor_monitor.site', 'search', [('site_code', '=', 'SITE-RPT-01')]) or [
        ex('sensor_monitor.site', 'create', {
            'name': 'S', 'partner_id': ex('res.partner', 'search', [], limit=1)[0],
            'site_code': 'SITE-RPT-01', 'vertical': 'cme_hospitalar'})]
    hub = ex('sensor_monitor.hub', 'search', [('hub_code', '=', 'HUB-RPT-02')]) or [
        ex('sensor_monitor.hub', 'create', {'name': 'H2', 'site_id': site[0], 'hub_code': 'HUB-RPT-02'})]
    ex('sensor_monitor.hub', 'write', [hub[0]], {'config_version_desejada': 5, 'config_version_aplicada': 3})

    with TestClient(app) as client:
        time.sleep(1.0)

        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        c.connect(MQTT_HOST, MQTT_PORT, 30)
        c.publish('sentinela/config/applied/hub/HUB-RPT-02',
                  json.dumps({'version': 5, 'aplicado_em': '2026-07-22T10:00:00+00:00', 'status': 'erro'}),
                  qos=1)
        c.disconnect()

        # sem sucesso a esperar/pollar: só damos tempo suficiente pro
        # subscriber processar (se fosse gravar) e conferimos que não gravou.
        time.sleep(2.0)
        aplicada = ex('sensor_monitor.hub', 'read', [hub[0]], fields=['config_version_aplicada'])[0]['config_version_aplicada']
        assert aplicada == 3
