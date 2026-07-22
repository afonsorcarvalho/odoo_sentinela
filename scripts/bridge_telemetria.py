"""Ponte telemetria MQTT → Timescale (cadência contínua / tempo real).

O Hub publica cada leitura em `sentinela/telemetria/<hub>/<coletor>/<sensor>`
(publicador_mqtt). Esta ponte assina esse tópico e insere cada leitura no
Timescale na hora → o trigger `sensor_reading_notify` dispara NOTIFY → a API
retransmite por SSE → o card do dashboard mostra o valor AO VIVO.

É o caminho de tempo real (o arquivo assinado + watcher_ingestao continua sendo
a persistência autoritativa; rode UM ou OUTRO para não duplicar leituras).

Env (defaults de dev):
  MQTT_HOST=localhost MQTT_PORT=1883
  TIMESCALE_DSN=postgresql://sentinela:sentinela@localhost:5433/sentinela
  ODOO_URL/ODOO_DB/ODOO_USER/ODOO_SENHA (para resolver site_code do coletor)
"""
import json
import os

import paho.mqtt.client as mqtt

from ingestao import odoo_cliente, timescale

MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))
DSN = os.environ.get('TIMESCALE_DSN', 'postgresql://sentinela:sentinela@localhost:5433/sentinela')
ODOO_URL = os.environ.get('ODOO_URL', 'http://localhost:8189')
ODOO_DB = os.environ.get('ODOO_DB', 'sentinela')
ODOO_USER = os.environ.get('ODOO_USER', 'admin')
ODOO_SENHA = os.environ.get('ODOO_SENHA', 'admin')

_cliente_odoo = None
_site_por_coletor = {}


def _site_code(coletor_id):
    if coletor_id not in _site_por_coletor:
        try:
            _site_por_coletor[coletor_id] = odoo_cliente.resolver_coletor(
                _cliente_odoo, coletor_id)['site_code']
        except Exception:
            _site_por_coletor[coletor_id] = None
    return _site_por_coletor[coletor_id]


def _on_message(conn):
    def handler(client, userdata, msg):
        try:
            partes = msg.topic.split('/')   # sentinela/telemetria/<hub>/<coletor>/<sensor>
            coletor_id, sensor_id = partes[3], partes[4]
            p = json.loads(msg.payload)
            site = _site_code(coletor_id)
            if not site:
                return
            leitura = {
                'timestamp': p['timestamp'], 'sensor_id': sensor_id,
                'area_id': p.get('area_id'), 'tipo_medida': p.get('tipo_medida'),
                'valor': p['valor'], 'unidade': p.get('unidade') or '',
                'protocolo_origem': p.get('protocolo_origem', '4-20ma'),
                'status_leitura': p.get('status', 'ok'),
            }
            timescale.inserir_leituras(conn, site, coletor_id, [leitura])
            print(f'[bridge] {sensor_id}={p["valor"]} {p.get("unidade","")} → Timescale ({site})')
        except Exception as e:
            print(f'[bridge] erro em {msg.topic}: {e}')
    return handler


def main():
    global _cliente_odoo
    _cliente_odoo = odoo_cliente.conectar(ODOO_URL, ODOO_DB, ODOO_USER, ODOO_SENHA)
    conn = timescale.conectar(DSN)
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.on_message = _on_message(conn)
    c.on_connect = lambda cl, u, f, rc, p=None: cl.subscribe('sentinela/telemetria/#', qos=0)
    c.connect(MQTT_HOST, MQTT_PORT, 30)
    print(f'[bridge] telemetria MQTT → Timescale (assinando sentinela/telemetria/#)')
    c.loop_forever()


if __name__ == '__main__':
    main()
