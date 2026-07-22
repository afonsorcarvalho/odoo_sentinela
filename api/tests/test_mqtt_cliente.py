import json
import os
import time

import paho.mqtt.client as mqtt

from api import mqtt as api_mqtt

MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))


def _ler_retido(topico, timeout=4.0):
    got = []
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='test-retido')
    c.on_message = lambda cl, u, m: got.append(m.payload)
    c.connect(MQTT_HOST, MQTT_PORT, 30)
    c.subscribe(topico, qos=1)
    c.loop_start()
    fim = time.time() + timeout
    while time.time() < fim and not got:
        time.sleep(0.05)
    c.loop_stop()
    return json.loads(got[0]) if got else None


def test_publicar_retido_fica_disponivel_para_novo_assinante():
    topico = 'sentinela/teste/retido'
    api_mqtt.publicar(topico, {'version': 7}, retain=True)
    assert _ler_retido(topico) == {'version': 7}
    # limpeza do retido
    api_mqtt.publicar(topico, {}, retain=True)
