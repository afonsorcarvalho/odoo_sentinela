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


def test_publicar_config_secret_errado_401():
    r = client.post(f'/internal/hub/{HUB_CODE}/publicar-config',
                    headers={'X-Config-Secret': 'errado'})
    assert r.status_code == 401


def test_publicar_config_grava_e_notifica_retido():
    # garante hub provisionado (reusa o fixture da Task 4)
    from api.tests.test_config_serializer import _prov_hub_modbus
    _prov_hub_modbus(get_cliente_servico())

    topico = f'sentinela/config/notify/hub/{HUB_CODE}'

    # Limpa o retido do tópico ANTES de assinar: o broker (mosquitto.conf
    # persistence true) guarda o retido entre execuções de teste, então sem
    # essa limpeza o assert abaixo poderia passar com uma mensagem STALE de
    # uma execução anterior, sem o router ter publicado nada agora.
    limpador = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    limpador.connect(MQTT_HOST, MQTT_PORT, 30)
    limpador.publish(topico, payload='', qos=1, retain=True)
    limpador.disconnect()
    time.sleep(0.3)

    got = []

    def _on_message(c, u, m):
        if m.payload:  # ignora o payload vazio usado para limpar o retido
            got.append(json.loads(m.payload))

    sub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    sub.on_message = _on_message
    sub.connect(MQTT_HOST, MQTT_PORT, 30)
    sub.subscribe(topico, qos=1)
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


def test_publicar_config_honra_version_explicita_no_body():
    # Prova do fix C1: a versão publicada é a que o caller (botão do Odoo)
    # manda explicitamente no body, não a lida de config_version_desejada
    # numa sessão XML-RPC separada — é isso que fecha o drift.
    from api.tests.test_config_serializer import _prov_hub_modbus
    _prov_hub_modbus(get_cliente_servico())

    topico = f'sentinela/config/notify/hub/{HUB_CODE}'

    limpador = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    limpador.connect(MQTT_HOST, MQTT_PORT, 30)
    limpador.publish(topico, payload='', qos=1, retain=True)
    limpador.disconnect()
    time.sleep(0.3)

    got = []

    def _on_message(c, u, m):
        if m.payload:
            got.append(json.loads(m.payload))

    sub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    sub.on_message = _on_message
    sub.connect(MQTT_HOST, MQTT_PORT, 30)
    sub.subscribe(topico, qos=1)
    sub.loop_start()
    time.sleep(0.3)

    r = client.post(f'/internal/hub/{HUB_CODE}/publicar-config',
                    headers={'X-Config-Secret': SECRET}, json={'version': 999})
    assert r.status_code == 200
    assert r.json()['version'] == 999

    fim = time.time() + 4
    while time.time() < fim and not got:
        time.sleep(0.05)
    sub.loop_stop()
    assert got and got[-1]['version'] == 999
