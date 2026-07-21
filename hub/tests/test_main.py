import textwrap
from datetime import datetime, timedelta, timezone
from threading import Event

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
