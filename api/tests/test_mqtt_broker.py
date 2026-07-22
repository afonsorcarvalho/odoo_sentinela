import json
import os
import time

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))


def test_broker_pub_sub_roundtrip():
    recebidas = []
    sub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='test-sub')
    sub.on_message = lambda c, u, m: recebidas.append((m.topic, m.payload))
    sub.connect(MQTT_HOST, MQTT_PORT, 30)
    sub.subscribe('sentinela/teste/#', qos=1)
    sub.loop_start()
    time.sleep(0.5)

    pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='test-pub')
    pub.connect(MQTT_HOST, MQTT_PORT, 30)
    pub.publish('sentinela/teste/x', json.dumps({'ok': 1}), qos=1, retain=False)
    pub.disconnect()

    for _ in range(40):
        if recebidas:
            break
        time.sleep(0.1)
    sub.loop_stop()
    assert any(t == 'sentinela/teste/x' for t, _ in recebidas)
