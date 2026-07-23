import textwrap
from datetime import datetime, timedelta, timezone
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from hub import config
from hub.assinador import AssinadorSoftware
from hub.arquivo_diario import ArquivoDiario
from hub import main as hub_main

TZ = timezone(timedelta(hours=-3))

CFG = """
    hub_id: HUB-0001
    coletor_id: COL-RS485-BUS0
    firmware_version: 0.1.0
    timezone_offset: "-03:00"
    intervalo_leitura_s: 0
    caminho_chave: {chave}
    caminho_dados: {dados}
    mqtt: {{host: localhost, port: 1883}}
    barramentos:
      - porta: /dev/ttyUSB0
        baud: 9600
        paridade: N
        stop_bits: 1
        dispositivos:
          - endereco: 1
            driver: n4aib16
            canais:
              - ch: 1
                sensor_id: SNR-EXP-TEMP-01
                area_id: AREA-EXPURGO
                tipo_medida: temperatura
                unidade: C
                protocolo_origem: 4-20ma
                map: {{in: [4, 20], out: [0, 100]}}
"""


class _LeitorFake:
    def ler_todos(self, agora):
        return [{
            "timestamp": agora, "sensor_id": "SNR-EXP-TEMP-01", "area_id": "AREA-EXPURGO",
            "tipo_medida": "temperatura", "valor": 42.0, "unidade": "C",
            "protocolo_origem": "4-20ma", "status_leitura": "ok",
            "cert_ver": 3, "cal_ganho": 0.965, "cal_offset": 0.33,
        }]
    def fechar(self):
        pass


class _PubFake:
    def __init__(self):
        self.n = 0
    def conectar(self):
        pass
    def publicar(self, *a):
        self.n += 1
    def fechar(self):
        pass


class _EnviadorFake:
    def __init__(self):
        self.varreduras = 0
    def varrer(self):
        self.varreduras += 1
        return []


def test_executar_chama_varrer_quando_ha_enviador(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(textwrap.dedent(CFG).format(chave=tmp_path / "k.pem", dados=tmp_path / "dados"))
    cfg = config.carregar_config(p)
    arq = ArquivoDiario(cfg.coletor_id, cfg.hub_id, cfg.firmware_version,
                        cfg.timezone_offset, cfg.caminho_dados, AssinadorSoftware(cfg.caminho_chave))
    envio = _EnviadorFake()
    agora = datetime(2026, 7, 21, 0, 1, tzinfo=TZ)
    hub_main.executar(cfg, _LeitorFake(), arq, _PubFake(), agora_fn=lambda: agora,
                      parar=Event(), max_ciclos=2, enviador=envio)
    # 2 ciclos + 1 varredura final no encerramento
    assert envio.varreduras == 3


def test_executar_grava_e_publica_e_sela_no_fim(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(textwrap.dedent(CFG).format(chave=tmp_path / "k.pem", dados=tmp_path / "dados"))
    cfg = config.carregar_config(p)
    arq = ArquivoDiario(cfg.coletor_id, cfg.hub_id, cfg.firmware_version,
                        cfg.timezone_offset, cfg.caminho_dados, AssinadorSoftware(cfg.caminho_chave))
    pub = _PubFake()
    agora = datetime(2026, 7, 21, 0, 1, tzinfo=TZ)
    hub_main.executar(cfg, _LeitorFake(), arq, pub, agora_fn=lambda: agora,
                      parar=Event(), max_ciclos=2)
    texto = arq.caminho("2026-07-21").read_text()
    assert texto.count("SNR-EXP-TEMP-01|") == 2   # 2 varreduras gravadas
    assert "# assinatura: " in texto              # selado no encerramento
    assert pub.n == 2                             # 2 publicações


def _cfg_com_sftp(tmp_path):
    return SimpleNamespace(
        timezone_offset='-03:00', caminho_chave=str(tmp_path / 'k.pem'), coletor_id='COL',
        hub_id='HUB', firmware_version='0.1.0', caminho_dados=str(tmp_path / 'dados'),
        cliente_id='CLI-1', site_id='SITE-1',
        mqtt_host='localhost', mqtt_port=1883, intervalo_leitura_s=5,
        sftp=SimpleNamespace(host='10.8.0.1', port=22, username='u', ssh_key_path='k',
                             remote_dir='/uploads'),
    )


def _monkeypatch_infra(monkeypatch, tmp_path):
    monkeypatch.setattr(hub_main.config_mod, 'carregar_config', lambda p: _cfg_com_sftp(tmp_path))
    monkeypatch.setattr(hub_main, 'AssinadorSoftware', lambda *a, **k: MagicMock())
    monkeypatch.setattr(hub_main, 'ArquivoDiario', lambda *a, **k: MagicMock())
    monkeypatch.setattr(hub_main, 'Leitor', lambda *a, **k: MagicMock())
    monkeypatch.setattr(hub_main, 'PublicadorMqtt', lambda *a, **k: MagicMock())


def test_main_com_sftp_sem_identity_levanta_systemexit(monkeypatch, tmp_path):
    _monkeypatch_infra(monkeypatch, tmp_path)
    with pytest.raises(SystemExit, match="identity"):
        hub_main.main(['--config', 'c.yaml'])


def test_main_com_sftp_identity_sem_hub_code_levanta_systemexit(monkeypatch, tmp_path):
    _monkeypatch_infra(monkeypatch, tmp_path)
    monkeypatch.setattr('hub.identidade_config.carregar_identidade',
                        lambda p: {'hub_id': 'HUB-0001'})  # sem hub_code
    with pytest.raises(SystemExit, match="hub_code"):
        hub_main.main(['--config', 'c.yaml', '--identity', 'identity.yaml'])


def test_main_constroi_enviador_sftp_real_com_assinatura_atual(monkeypatch, tmp_path):
    # Regressão de wiring: os testes acima nunca chegam na construção do
    # EnviadorSftp (levantam SystemExit antes). Este teste deixa a classe
    # REAL (não mockada) e força o main() a passar por essa linha, para que
    # uma quebra de assinatura em hub/main.py (ex.: faltar hub_id=) estoure
    # um TypeError aqui — e não passe despercebida como antes.
    _monkeypatch_infra(monkeypatch, tmp_path)
    monkeypatch.setattr('hub.identidade_config.carregar_identidade',
                        lambda p: {'hub_code': 'HUB-0001'})
    monkeypatch.setattr('hub.identidade_ssh.carregar_ou_criar_chave_ssh', lambda p: None)
    monkeypatch.setattr('hub.agente_config.AgenteControle',
                        lambda **k: SimpleNamespace(iniciar=lambda: None, parar=lambda: None))
    capturado = {}

    def _executar_fake(config, leitor, arquivo, publicador, **kwargs):
        capturado['enviador'] = kwargs.get('enviador')

    monkeypatch.setattr(hub_main, 'executar', _executar_fake)

    hub_main.main(['--config', 'c.yaml', '--identity', 'identity.yaml'])

    from hub.enviador_sftp import EnviadorSftp
    enviador = capturado['enviador']
    assert isinstance(enviador, EnviadorSftp)
    assert enviador._coletor_id == 'COL'
    assert enviador._cliente_id == 'CLI-1'
    assert enviador._site_id == 'SITE-1'
    assert enviador._hub_id == 'HUB'
