"""Publica cada leitura no broker MQTT local. Nunca propaga falha de rede —
o arquivo assinado é a fonte de verdade; MQTT é conveniência de tempo real.
"""
import json


class PublicadorMqtt:
    def __init__(self, host, port, client=None):
        if client is None:
            import paho.mqtt.client as mqtt
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client = client
        self._host = host
        self._port = port

    def conectar(self):
        try:
            self._client.connect(self._host, self._port)
        except OSError:
            pass  # sem broker agora; publicar vira no-op resiliente

    def publicar(self, hub_id, coletor_id, leitura):
        topico = f"sentinela/telemetria/{hub_id}/{coletor_id}/{leitura['sensor_id']}"
        payload = json.dumps({
            "timestamp": leitura["timestamp"].isoformat(timespec="seconds"),
            "tipo_medida": leitura["tipo_medida"],
            "valor": leitura["valor"],
            "unidade": leitura["unidade"],
            "area_id": leitura["area_id"],
            "status": leitura["status_leitura"],
        })
        try:
            self._client.publish(topico, payload, qos=0)
            return topico
        except OSError:
            return None

    def fechar(self):
        try:
            self._client.disconnect()
        except OSError:
            pass
