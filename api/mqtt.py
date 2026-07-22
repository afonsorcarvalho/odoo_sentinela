import json
import os

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))
_KEEPALIVE = 30


def publicar(topico, payload, retain=False):
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.connect(MQTT_HOST, MQTT_PORT, _KEEPALIVE)
    c.loop_start()
    try:
        info = c.publish(topico, json.dumps(payload), qos=1, retain=retain)
        info.wait_for_publish(timeout=5)
    finally:
        c.loop_stop()
        c.disconnect()


class OuvinteMqtt:
    def __init__(self, on_mensagem):
        self._on = on_mensagem
        self._topicos = []
        self._c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._c.on_message = self._despachar
        self._c.on_connect = self._on_connect

    def _despachar(self, cliente, userdata, msg):
        try:
            dados = json.loads(msg.payload) if msg.payload else {}
        except json.JSONDecodeError:
            return
        self._on(msg.topic, dados)

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        # re-assina em toda (re)conexão — inclusive após o broker cair e voltar,
        # quando a assinatura anterior se perde.
        for t in self._topicos:
            client.subscribe(t, qos=1)

    def iniciar(self, topicos):
        self._topicos = topicos
        # connect_async + loop_start: não bloqueia o boot da API se o broker
        # estiver indisponível; a reconexão automática assina via on_connect.
        self._c.connect_async(MQTT_HOST, MQTT_PORT, _KEEPALIVE)
        self._c.loop_start()

    def parar(self):
        self._c.loop_stop()
        if self._c.is_connected():
            self._c.disconnect()
