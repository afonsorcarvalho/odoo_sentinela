import json
import os
import time

import paho.mqtt.client as mqtt
from fastapi.testclient import TestClient

from api.main import app
from api.odoo import get_cliente_servico
from ingestao import odoo_cliente, provisionar_demo

client = TestClient(app)
SECRET = os.environ.get('CONFIG_PUBLISH_SECRET', 'test-secret')
MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))
HUB_CODE = provisionar_demo.HUB_CODE  # 'HUB-DEMO-01' — o fixture da Task 4 reusa provisionar_demo


def test_publicar_config_sem_secret_401():
    r = client.post(f'/internal/hub/{HUB_CODE}/publicar-config')
    assert r.status_code == 401


def test_publicar_config_grava_e_notifica_retido():
    # garante hub provisionado (reusa o fixture da Task 4)
    from api.tests.test_config_serializer import _prov_hub_modbus
    _prov_hub_modbus(get_cliente_servico())

    got = []
    sub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    sub.on_message = lambda c, u, m: got.append(json.loads(m.payload))
    sub.connect(MQTT_HOST, MQTT_PORT, 30)
    sub.subscribe(f'sentinela/config/notify/hub/{HUB_CODE}', qos=1)
    sub.loop_start()
    time.sleep(0.3)

    r = client.post(f'/internal/hub/{HUB_CODE}/publicar-config',
                    headers={'X-Config-Secret': SECRET})
    assert r.status_code == 200
    versao = r.json()['version']

    fim = time.time() + 4
    while time.time() < fim and not got:
        time.sleep(0.05)
    sub.loop_stop()
    assert got and got[-1]['version'] == versao
