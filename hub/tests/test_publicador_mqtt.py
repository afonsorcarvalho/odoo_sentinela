import json
from datetime import datetime, timedelta, timezone

from hub.publicador_mqtt import PublicadorMqtt

TZ = timezone(timedelta(hours=-3))


class _ClientFake:
    def __init__(self):
        self.publicados = []
        self.conectado = False
    def connect(self, host, port):
        self.conectado = True
    def publish(self, topico, payload, qos=0):
        self.publicados.append((topico, payload, qos))
    def disconnect(self):
        pass


def _leitura():
    return {
        "timestamp": datetime(2026, 7, 21, 0, 1, tzinfo=TZ), "sensor_id": "SNR-EXP-TEMP-01",
        "area_id": "AREA-EXPURGO", "tipo_medida": "temperatura", "valor": 19.8,
        "unidade": "C", "protocolo_origem": "4-20ma", "status_leitura": "ok",
    }


def test_publica_no_topico_e_payload_corretos():
    cli = _ClientFake()
    pub = PublicadorMqtt("localhost", 1883, client=cli)
    pub.conectar()
    topico = pub.publicar("HUB-0001", "COL-RS485-BUS0", _leitura())
    assert topico == "sentinela/telemetria/HUB-0001/COL-RS485-BUS0/SNR-EXP-TEMP-01"
    (t, payload, qos) = cli.publicados[0]
    dados = json.loads(payload)
    assert dados["valor"] == 19.8
    assert dados["status"] == "ok"
    assert dados["timestamp"] == "2026-07-21T00:01:00-03:00"


def test_falha_de_publish_nao_propaga():
    class Explode(_ClientFake):
        def publish(self, *a, **k):
            raise OSError("broker caiu")
    pub = PublicadorMqtt("localhost", 1883, client=Explode())
    pub.conectar()
    assert pub.publicar("HUB-0001", "COL-RS485-BUS0", _leitura()) is None  # não levanta
