import json
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock

import yaml

from hub.agente_config import AgenteControle
from hub.tests._fixtures_config import IDENTIDADE, OPERACIONAL  # reusa Task 2 (ver nota)


def _agente(tmp_path, publish, sftp_baixar):
    client = MagicMock()
    client.publish = publish
    ag = AgenteControle(
        hub_code='HUB-EXP', identidade=IDENTIDADE, sftp_baixar=sftp_baixar,
        reconfigurar=Event(), caminho_config=str(tmp_path / 'config.yaml'),
        estado_path=str(tmp_path / 'estado.json'), fw='0.1.0', client=client,
        agora_fn=lambda: __import__('datetime').datetime(2026, 7, 22, 10, 0, 0,
                       tzinfo=__import__('datetime').timezone.utc))
    return ag


def test_notify_nova_versao_baixa_aplica_e_reporta(tmp_path):
    publicados = []
    def publish(topico, payload, **k): publicados.append((topico, json.loads(payload)))
    def sftp_baixar(remoto, local):
        Path(local).write_text(yaml.safe_dump(OPERACIONAL))  # simula o download
    ag = _agente(tmp_path, publish, sftp_baixar)
    ag.processar_notify({'version': 4})
    # efetivo escrito e carregável
    assert (tmp_path / 'config.yaml').exists()
    # estado avançou e persistiu
    assert ag.aplicada == 4
    assert json.loads((tmp_path / 'estado.json').read_text())['config_version_aplicada'] == 4
    # reconfigurar sinalizado
    assert ag._reconfigurar.is_set()
    # applied publicado com +00:00 (não Z) e status ok
    applied = [p for t, p in publicados if t.endswith('applied/hub/HUB-EXP')][-1]
    assert applied['version'] == 4 and applied['status'] == 'ok'
    assert applied['aplicado_em'].endswith('+00:00') and 'Z' not in applied['aplicado_em']


def test_notify_versao_antiga_e_noop(tmp_path):
    ag = _agente(tmp_path, lambda *a, **k: None, lambda *a, **k: None)
    ag.aplicada = 5
    ag.processar_notify({'version': 3})
    assert ag.aplicada == 5 and not ag._reconfigurar.is_set()


def test_erro_no_download_publica_status_erro(tmp_path):
    publicados = []
    def publish(topico, payload, **k): publicados.append((topico, json.loads(payload)))
    def sftp_baixar(remoto, local): raise OSError('sem rede')
    ag = _agente(tmp_path, publish, sftp_baixar)
    ag.processar_notify({'version': 7})
    assert ag.aplicada == 0  # não avançou
    applied = [p for t, p in publicados if 'applied' in t][-1]
    assert applied['version'] == 7 and applied['status'] == 'erro'


def test_heartbeat_inclui_versao_aplicada(tmp_path):
    ag = _agente(tmp_path, lambda *a, **k: None, lambda *a, **k: None)
    ag.aplicada = 6
    hb = ag.heartbeat_payload()
    assert hb['estado'] == 'online' and hb['config_version_aplicada'] == 6 and 'heartbeat_ts' in hb


def test_notify_payload_nao_dict_e_ignorado(tmp_path):
    ag = _agente(tmp_path, lambda *a, **k: None, lambda *a, **k: None)
    ag.processar_notify(42)
    ag.processar_notify(None)
    ag.processar_notify([1, 2])
    assert ag.aplicada == 0


def test_estado_corrompido_carrega_zero(tmp_path):
    estado_path = tmp_path / 'estado.json'
    estado_path.write_text('isto nao e json valido {{{')
    ag = _agente(tmp_path, lambda *a, **k: None, lambda *a, **k: None)
    assert ag.aplicada == 0


def test_apply_republica_status_com_versao_nova(tmp_path):
    publicados = []
    def publish(topico, payload, **k): publicados.append((topico, json.loads(payload), k))
    def sftp_baixar(remoto, local):
        Path(local).write_text(yaml.safe_dump(OPERACIONAL))
    ag = _agente(tmp_path, publish, sftp_baixar)
    ag.processar_notify({'version': 4})
    status_pub = [p for t, p, k in publicados if t == 'sentinela/status/hub/HUB-EXP']
    assert status_pub, 'status retido deveria ter sido republicado após applied:ok'
    assert status_pub[-1]['config_version_aplicada'] == 4
    # confere que foi publicado retido
    status_kwargs = [k for t, p, k in publicados if t == 'sentinela/status/hub/HUB-EXP']
    assert status_kwargs[-1].get('retain') is True


def test_config_invalido_nao_avanca_nem_reporta_ok(tmp_path):
    publicados = []
    def publish(topico, payload, **k): publicados.append((topico, json.loads(payload)))
    operacional_invalido = {
        'version': 7, 'intervalo_leitura_s': 5,
        'barramentos': [{'porta': '/dev/ttyUSB0', 'baud': 9600, 'paridade': 'N', 'stop_bits': 1,
            'dispositivos': [{'endereco': 1, 'driver': 'n4aib16', 'canais': [
                {'ch': 1, 'sensor_id': 'SNR-EXP-TEMP-01', 'area_id': 'AREA-EXPURGO',
                 'tipo_medida': 'temperatura', 'unidade': 'C', 'protocolo_origem': '4-20ma'}
                # falta 'map' -> carregar_config deve levantar (KeyError)
            ]}]}],
    }
    def sftp_baixar(remoto, local):
        Path(local).write_text(yaml.safe_dump(operacional_invalido))
    ag = _agente(tmp_path, publish, sftp_baixar)
    ag.processar_notify({'version': 7})
    applied = [p for t, p in publicados if t.endswith('applied/hub/HUB-EXP')][-1]
    assert applied['status'] == 'erro'
    assert ag.aplicada == 0
    assert not (tmp_path / 'config.yaml').exists()
    # não deixa lixo residual
    assert not (tmp_path / 'config.yaml.novo').exists()
    assert not (tmp_path / 'config.yaml.baixando').exists()
