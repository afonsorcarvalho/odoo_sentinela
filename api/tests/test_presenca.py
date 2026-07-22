import os
import time

import paho.mqtt.client as mqtt
import json
from fastapi.testclient import TestClient

from api.main import app

MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))


def test_status_reflete_presenca_publicada():
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.connect(MQTT_HOST, MQTT_PORT, 30)
    c.publish('sentinela/status/hub/HUB-PRES-01',
              json.dumps({'estado': 'online', 'heartbeat_ts': time.time()}),
              qos=1, retain=True)
    c.disconnect()

    # Starlette 0.49.x só dispara os eventos de startup do FastAPI dentro do
    # context manager (`__enter__` chama `wait_startup`); um TestClient(app)
    # solto nunca roda o RASTREADOR.iniciar() do startup. Por isso o sleep
    # (que dá tempo do retido chegar) precisa ficar dentro do `with`, depois
    # da subscription já ter sido feita.
    with TestClient(app) as client:
        time.sleep(1.0)  # deixa o rastreador (startup) consumir

        r = client.get('/internal/hub/HUB-PRES-01/status')
        assert r.status_code == 200
        assert r.json()['estado'] == 'online' and r.json()['stale'] is False

    # limpeza do retido
    c2 = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c2.connect(MQTT_HOST, MQTT_PORT, 30)
    c2.publish('sentinela/status/hub/HUB-PRES-01', '', qos=1, retain=True)
    c2.disconnect()
