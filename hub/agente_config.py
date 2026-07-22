"""AgenteControle: cliente MQTT do control-plane (LWT + heartbeat) + notify->download->apply->report."""
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import yaml

from hub.config import carregar_config
from hub.identidade_config import escrever_config_efetivo, fundir

_KEEPALIVE = 30


def _iso_utc(agora_fn):
    return agora_fn().astimezone(timezone.utc).isoformat()  # +00:00, nunca Z


class AgenteControle:
    def __init__(self, hub_code, identidade, sftp_baixar, reconfigurar, caminho_config,
                 estado_path, fw='0.1.0', client=None, mqtt_host='localhost',
                 mqtt_port=1883, agora_fn=None, heartbeat_intervalo_s=30):
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
        self._hb_intervalo = heartbeat_intervalo_s
        self._hb_thread = None
        self._parar_hb = threading.Event()
        self.aplicada = self._carregar_estado()
        if client is None:
            import paho.mqtt.client as mqtt
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client = client

    def _carregar_estado(self):
        if self._estado_path.exists():
            try:
                return int(json.loads(self._estado_path.read_text()).get('config_version_aplicada', 0))
            except (json.JSONDecodeError, ValueError, OSError):
                return 0
        return 0

    def _persistir_estado(self):
        self._estado_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._estado_path.with_name(self._estado_path.name + '.tmp')
        tmp.write_text(json.dumps({'config_version_aplicada': self.aplicada}))
        os.replace(tmp, self._estado_path)

    def _publicar(self, sufixo, payload, retain=False):
        self._client.publish(f'sentinela/config/{sufixo}/hub/{self._code}',
                             json.dumps(payload), qos=1, retain=retain)

    def _publicar_status(self):
        """Republica o status retido (heartbeat + config_version_aplicada).

        Chamado no connect, logo após aplicar um config com sucesso, e
        periodicamente (thread de heartbeat) — é o que mantém a rede de
        segurança do servidor (liveness) viva e o retido em dia.
        """
        self._client.publish(f'sentinela/status/hub/{self._code}',
                             json.dumps(self.heartbeat_payload()), qos=1, retain=True)

    def heartbeat_payload(self):
        return {'estado': 'online', 'heartbeat_ts': _iso_utc(self._agora),
                'fw': self._fw, 'config_version_aplicada': self.aplicada}

    def processar_notify(self, dados):
        if not isinstance(dados, dict):
            return
        versao = dados.get('version')
        if versao is None or versao <= self.aplicada:
            return
        self._client.publish(f'sentinela/config/ack/hub/{self._code}',
                             json.dumps({'version': versao, 'recebido_em': _iso_utc(self._agora)}),
                             qos=1)
        local_tmp = f'{self._caminho_config}.baixando'
        caminho_temp = f'{self._caminho_config}.novo'
        try:
            self._baixar(f'/config/{self._code}/config-v{versao}.yaml', local_tmp)
            operacional = yaml.safe_load(Path(local_tmp).read_text())
            merged = fundir(self._identidade, operacional)
            escrever_config_efetivo(merged, caminho_temp)
            # valida ANTES de comprometer: um config que não carrega não pode
            # virar o config.yaml real nem ser reportado como applied:ok.
            carregar_config(caminho_temp)
            os.replace(caminho_temp, self._caminho_config)
            self.aplicada = versao
            self._persistir_estado()
            self._reconfigurar.set()
            self._publicar('applied', {'version': versao, 'aplicado_em': _iso_utc(self._agora),
                                       'status': 'ok'})
            self._publicar_status()
        except Exception as e:
            self._publicar('applied', {'version': versao, 'aplicado_em': _iso_utc(self._agora),
                                       'status': 'erro', 'detalhe': str(e)[:200]})
        finally:
            for residual in (local_tmp, caminho_temp):
                try:
                    os.remove(residual)
                except OSError:
                    pass

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        client.subscribe(f'sentinela/config/notify/hub/{self._code}', qos=1)
        self._publicar_status()

    def _on_message(self, client, userdata, msg):
        try:
            self.processar_notify(json.loads(msg.payload) if msg.payload else {})
        except Exception:
            pass

    def _loop_heartbeat(self):
        while not self._parar_hb.wait(self._hb_intervalo):
            try:
                if self._client.is_connected():
                    self._publicar_status()
            except Exception:
                pass

    def iniciar(self):
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.will_set(f'sentinela/status/hub/{self._code}',
                             json.dumps({'estado': 'offline'}), qos=1, retain=True)
        self._client.connect_async(self._host, self._port, _KEEPALIVE)
        self._client.loop_start()
        self._parar_hb.clear()
        self._hb_thread = threading.Thread(target=self._loop_heartbeat, daemon=True)
        self._hb_thread.start()

    def parar(self):
        self._parar_hb.set()
        if self._hb_thread is not None:
            self._hb_thread.join(timeout=1)
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except OSError:
            pass
