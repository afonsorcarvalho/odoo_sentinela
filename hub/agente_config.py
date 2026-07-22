"""AgenteControle: cliente MQTT do control-plane (LWT + heartbeat) + notify->download->apply->report."""
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from hub.identidade_config import escrever_config_efetivo, fundir

_KEEPALIVE = 30


def _iso_utc(agora_fn):
    return agora_fn().astimezone(timezone.utc).isoformat()  # +00:00, nunca Z


class AgenteControle:
    def __init__(self, hub_code, identidade, sftp_baixar, reconfigurar, caminho_config,
                 estado_path, fw='0.1.0', client=None, mqtt_host='localhost',
                 mqtt_port=1883, agora_fn=None):
        self._code = hub_code
        self._identidade = identidade
        self._baixar = sftp_baixar
        self._reconfigurar = reconfigurar
        self._caminho_config = caminho_config
        self._estado_path = Path(estado_path)
        self._fw = fw
        self._host = mqtt_host
        self._port = mqtt_port
        self._agora = agora_fn or (lambda: datetime.now(timezone.utc))
        self.aplicada = self._carregar_estado()
        if client is None:
            import paho.mqtt.client as mqtt
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client = client

    def _carregar_estado(self):
        if self._estado_path.exists():
            return int(json.loads(self._estado_path.read_text()).get('config_version_aplicada', 0))
        return 0

    def _persistir_estado(self):
        self._estado_path.parent.mkdir(parents=True, exist_ok=True)
        self._estado_path.write_text(json.dumps({'config_version_aplicada': self.aplicada}))

    def _publicar(self, sufixo, payload, retain=False):
        self._client.publish(f'sentinela/config/{sufixo}/hub/{self._code}',
                             json.dumps(payload), qos=1, retain=retain)

    def heartbeat_payload(self):
        return {'estado': 'online', 'heartbeat_ts': _iso_utc(self._agora),
                'fw': self._fw, 'config_version_aplicada': self.aplicada}

    def processar_notify(self, dados):
        versao = dados.get('version')
        if versao is None or versao <= self.aplicada:
            return
        self._client.publish(f'sentinela/config/ack/hub/{self._code}',
                             json.dumps({'version': versao, 'recebido_em': _iso_utc(self._agora)}),
                             qos=1)
        try:
            local_tmp = f'{self._caminho_config}.baixando'
            self._baixar(f'/config/{self._code}/config-v{versao}.yaml', local_tmp)
            operacional = yaml.safe_load(Path(local_tmp).read_text())
            merged = fundir(self._identidade, operacional)
            escrever_config_efetivo(merged, self._caminho_config)
            self.aplicada = versao
            self._persistir_estado()
            self._reconfigurar.set()
            self._publicar('applied', {'version': versao, 'aplicado_em': _iso_utc(self._agora),
                                       'status': 'ok'})
        except Exception as e:
            self._publicar('applied', {'version': versao, 'aplicado_em': _iso_utc(self._agora),
                                       'status': 'erro', 'detalhe': str(e)[:200]})

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        client.subscribe(f'sentinela/config/notify/hub/{self._code}', qos=1)
        client.publish(f'sentinela/status/hub/{self._code}',
                      json.dumps(self.heartbeat_payload()), qos=1, retain=True)

    def _on_message(self, client, userdata, msg):
        try:
            self.processar_notify(json.loads(msg.payload) if msg.payload else {})
        except json.JSONDecodeError:
            pass

    def iniciar(self):
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.will_set(f'sentinela/status/hub/{self._code}',
                             json.dumps({'estado': 'offline'}), qos=1, retain=True)
        self._client.connect_async(self._host, self._port, _KEEPALIVE)
        self._client.loop_start()

    def parar(self):
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except OSError:
            pass
