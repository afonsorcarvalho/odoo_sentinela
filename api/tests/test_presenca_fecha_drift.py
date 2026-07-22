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


def test_heartbeat_com_versao_aplicada_fecha_drift():
    cliente = get_cliente_servico()
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)
    site = ex('sensor_monitor.site', 'search', [('site_code', '=', 'SITE-HB-01')]) or [
        ex('sensor_monitor.site', 'create', {
            'name': 'S', 'partner_id': ex('res.partner', 'search', [], limit=1)[0],
            'site_code': 'SITE-HB-01', 'vertical': 'cme_hospitalar'})]
    hub = ex('sensor_monitor.hub', 'search', [('hub_code', '=', 'HUB-HB-01')]) or [
        ex('sensor_monitor.hub', 'create', {'name': 'H', 'site_id': site[0], 'hub_code': 'HUB-HB-01'})]
    ex('sensor_monitor.hub', 'write', [hub[0]], {'config_version_desejada': 9, 'config_version_aplicada': 0})

    # Publica o retido ANTES do TestClient: o objetivo do teste é o caminho
    # "retido consumido no subscribe" (a rede de segurança real quando o
    # 'applied' one-shot se perdeu) — não entrega ao vivo. Mesmo motivo do
    # gotcha documentado em test_presenca.py/test_config_report.py: no
    # Starlette 0.49.x os eventos de startup (RASTREADOR.iniciar() assina o
    # tópico) só disparam dentro do context manager do TestClient, então a
    # subscrição só existe depois do `with` abrir — o retido garante que a
    # mensagem chega mesmo assim.
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.connect(MQTT_HOST, MQTT_PORT, 30)
    c.publish('sentinela/status/hub/HUB-HB-01', json.dumps({
        'estado': 'online', 'heartbeat_ts': '2026-07-22T10:00:00+00:00',
        'fw': '0.1.0', 'config_version_aplicada': 9}), qos=1, retain=True)
    c.disconnect()

    with TestClient(app) as client:
        time.sleep(1.0)  # deixa o RASTREADOR (startup) consumir o retido

        fim = time.time() + 8
        aplicada = 0
        while time.time() < fim:
            aplicada = ex('sensor_monitor.hub', 'read', [hub[0]], fields=['config_version_aplicada'])[0]['config_version_aplicada']
            if aplicada == 9:
                break
            time.sleep(0.3)

        # limpa o retido
        c2 = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        c2.connect(MQTT_HOST, MQTT_PORT, 30)
        c2.publish('sentinela/status/hub/HUB-HB-01', '', qos=1, retain=True)
        c2.disconnect()
        assert aplicada == 9
