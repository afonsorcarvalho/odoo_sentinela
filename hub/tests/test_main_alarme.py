# hub/tests/test_main_alarme.py
from datetime import datetime, timezone
from threading import Event

from hub import main as main_mod
from hub.detector_alarme import DetectorAlarme
from hub.config import CanalConfig, DispositivoConfig, BarramentoConfig, HubConfig

TS = datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)


def _config():
    canal = CanalConfig(ch=1, sensor_id="SNR-T-01", area_id="AREA-T",
                        tipo_medida="temperatura", unidade="C", protocolo_origem="4-20ma",
                        limite_min=18.0, limite_max=25.0)
    disp = DispositivoConfig(endereco=1, driver="n4aib16", canais=[canal])
    bus = BarramentoConfig(porta="/dev/ttyUSB0", baud=9600, paridade="N", stop_bits=1,
                           dispositivos=[disp])
    return HubConfig(hub_id="HUB-T", coletor_id="COL-T", firmware_version="0.1.0",
                     timezone_offset="-03:00", intervalo_leitura_s=0, caminho_chave="/tmp/k",
                     caminho_dados="/tmp/d", mqtt_host="localhost", mqtt_port=1883,
                     barramentos=[bus], alarme_n=3, alarme_margem=0.5)


def test_montar_limites_extrai_da_config():
    limites = main_mod.montar_limites(_config())
    assert limites == {"SNR-T-01": {"min": 18.0, "max": 25.0}}


class _LeitorFake:
    def __init__(self, sequencia): self._seq = sequencia; self._i = 0
    def ler_todos(self, agora):
        vals = self._seq[min(self._i, len(self._seq) - 1)]; self._i += 1
        return [{"sensor_id": "SNR-T-01", "area_id": "AREA-T", "tipo_medida": "temperatura",
                 "valor": v, "unidade": "C", "protocolo_origem": "4-20ma",
                 "status_leitura": "ok", "cert_ver": 0, "cal_ganho": 1.0, "cal_offset": 0.0,
                 "timestamp": agora} for v in [vals]]
    def fechar(self): pass


class _ArquivoFake:
    def __init__(self): self.leituras = []
    def recuperar_pendentes(self, hoje): pass
    def registrar(self, leitura): self.leituras.append(leitura)
    def selar(self, data=None, caminho=None): pass


class _ArquivoAlarmesFake(_ArquivoFake):
    def __init__(self): self.eventos = []
    def registrar(self, *a, **k): pass
    def registrar_evento(self, evento): self.eventos.append(evento)


class _PubFake:
    def __init__(self): self.alarmes = []
    def conectar(self): pass
    def publicar(self, *a, **k): pass
    def publicar_alarme(self, hub_id, coletor_id, evento): self.alarmes.append(evento)
    def fechar(self): pass


def test_loop_emite_evento_para_arquivo_e_mqtt():
    cfg = _config()
    leitor = _LeitorFake([30.0, 30.0, 30.0])   # 3 leituras fora -> 1 entrada
    arquivo = _ArquivoFake()
    arquivo_alarmes = _ArquivoAlarmesFake()
    pub = _PubFake()
    detector = DetectorAlarme(main_mod.montar_limites(cfg), n=cfg.alarme_n, margem=cfg.alarme_margem)
    main_mod.executar(cfg, leitor, arquivo, pub, agora_fn=lambda: TS, parar=Event(),
                      max_ciclos=3, detector=detector, arquivo_alarmes=arquivo_alarmes)
    assert len(arquivo_alarmes.eventos) == 1
    assert arquivo_alarmes.eventos[0]["tipo_evento"] == "entrada_alarme"
    assert len(pub.alarmes) == 1
