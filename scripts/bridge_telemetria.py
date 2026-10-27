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
_coletor_odoo_id = {}
_sensor_odoo = {}


def _obter_cliente_odoo():
    """Conexão preguiçosa: só conecta quando precisa; reconecta após invalidação."""
    global _cliente_odoo
    if _cliente_odoo is None:
        _cliente_odoo = odoo_cliente.conectar(ODOO_URL, ODOO_DB, ODOO_USER, ODOO_SENHA)
    return _cliente_odoo


def _invalidar_cliente_odoo():
    global _cliente_odoo
    _cliente_odoo = None


def _site_code(coletor_id):
    if coletor_id not in _site_por_coletor:
        try:
            _site_por_coletor[coletor_id] = odoo_cliente.resolver_coletor(
                _obter_cliente_odoo(), coletor_id)['site_code']
        except Exception:
            _site_por_coletor[coletor_id] = None
    return _site_por_coletor[coletor_id]


def _ids_odoo(coletor_code, sensor_code):
    """(sensor_id, area_id, coletor_id) no Odoo, com cache (só sucessos)."""
    cliente = _obter_cliente_odoo()
    if coletor_code not in _coletor_odoo_id:
        _coletor_odoo_id[coletor_code] = odoo_cliente.resolver_coletor(cliente, coletor_code)['id']
    if sensor_code not in _sensor_odoo:
        _sensor_odoo[sensor_code] = odoo_cliente.resolver_sensor(cliente, sensor_code)
    sensor = _sensor_odoo[sensor_code]
    return sensor['id'], sensor['area_id'], _coletor_odoo_id[coletor_code]


def _alarme_no_odoo(coletor_code, sensor_code, p):
    """Abre/fecha o alarm.event ao vivo (sem hash; a ingestão do arquivo
    assinado reconcilia pelo mesmo sensor+timestamp e carimba o hash).
    Nunca propaga exceção: falha do Odoo não pode derrubar a ponte nem o toast."""
    try:
        sensor_id, area_id, coletor_id = _ids_odoo(coletor_code, sensor_code)
        evento = {
            'timestamp': p['timestamp'],
            'tipo_evento': p.get('tipo_evento'),
            'tipo_violacao': p.get('tipo_violacao'),
            'valor': p.get('valor'),
            'limite_min_vigente': p.get('limite_min'),
            'limite_max_vigente': p.get('limite_max'),
        }
        cliente = _obter_cliente_odoo()
        if evento['tipo_evento'] == 'entrada_alarme':
            odoo_cliente.processar_entrada_alarme(
                cliente, evento, sensor_id, area_id, coletor_id, None)
        elif evento['tipo_evento'] == 'saida_alarme':
            odoo_cliente.processar_saida_alarme(cliente, evento, sensor_id)
    except Exception as e:
        print(f'[bridge] alarme {sensor_code}: falha ao registrar no Odoo: {e!r}')
        if not isinstance(e, ValueError):   # ValueError = cadastro ausente, não conexão
            _invalidar_cliente_odoo()


def _on_message(conn):
    def handler(client, userdata, msg):
        try:
            partes = msg.topic.split('/')   # sentinela/telemetria|alarme/<hub>/<coletor>/<sensor>
            if partes[1] == 'alarme':
                coletor_id, sensor_code = partes[3], partes[4]
                p = json.loads(msg.payload)
                site = _site_code(coletor_id)
                if not site:
                    return
                evento = {**p, "site_id": site, "tipo": "alarme_ao_vivo"}
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_notify('alarme_ao_vivo', %s)", (json.dumps(evento),))
                conn.commit()
                print(f'[bridge] ALARME {p.get("sensor_id")} {p.get("tipo_evento")} → SSE ({site})')
                # Depois do NOTIFY: Odoo lento/fora não atrasa nem impede o toast.
                _alarme_no_odoo(coletor_id, sensor_code, p)
                return
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
    conn = timescale.conectar(DSN)
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.on_message = _on_message(conn)
    c.on_connect = lambda cl, u, f, rc, p=None: (
        cl.subscribe('sentinela/telemetria/#', qos=0),
        cl.subscribe('sentinela/alarme/#', qos=0),
    )
    c.connect(MQTT_HOST, MQTT_PORT, 30)
    print(f'[bridge] telemetria+alarme MQTT → Timescale (assinando sentinela/telemetria/# e sentinela/alarme/#)')
    c.loop_forever()


if __name__ == '__main__':
    main()
