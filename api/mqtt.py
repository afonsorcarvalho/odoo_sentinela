import json
import os
import threading

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))
_KEEPALIVE = 30


def publicar(topico, payload, retain=False):
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.connect(MQTT_HOST, MQTT_PORT, _KEEPALIVE)
    info = c.publish(topico, json.dumps(payload), qos=1, retain=retain)
    info.wait_for_publish(timeout=5)
    c.disconnect()


class OuvinteMqtt:
    def __init__(self, on_mensagem):
        self._on = on_mensagem
        self._c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._c.on_message = self._despachar

    def _despachar(self, cliente, userdata, msg):
        try:
            dados = json.loads(msg.payload) if msg.payload else {}
        except json.JSONDecodeError:
            return
        self._on(msg.topic, dados)

    def iniciar(self, topicos):
        self._c.connect(MQTT_HOST, MQTT_PORT, _KEEPALIVE)
        for t in topicos:
            self._c.subscribe(t, qos=1)
        self._c.loop_start()

    def parar(self):
        self._c.loop_stop()
        if self._c.is_connected():
            self._c.disconnect()
