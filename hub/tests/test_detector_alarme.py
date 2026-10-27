import json
from datetime import datetime, timezone

from hub.detector_alarme import DetectorAlarme

TS = datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)


def _leitura(valor, status="ok", sensor="S1"):
    return {"sensor_id": sensor, "area_id": "A1", "tipo_medida": "temperatura",
            "valor": valor, "status_leitura": status, "timestamp": TS}


def _det(**kw):
    limites = {"S1": {"min": 18.0, "max": 25.0}}
    return DetectorAlarme(limites, n=3, margem=0.5, **kw)


def test_entrada_apos_n_leituras_fora():
    d = _det()
    assert d.avaliar(_leitura(30.0)) == []      # 1 fora
    assert d.avaliar(_leitura(30.0)) == []      # 2 fora
    eventos = d.avaliar(_leitura(30.0))         # 3 fora -> entrada
    assert len(eventos) == 1
    e = eventos[0]
    assert e["tipo_evento"] == "entrada_alarme"
    assert e["tipo_violacao"] == "acima_limite"
    assert e["valor"] == 30.0
    assert e["limite_max_vigente"] == 25.0
    assert e["sensor_id"] == "S1"


def test_dentro_zera_contador():
    d = _det()
    d.avaliar(_leitura(30.0)); d.avaliar(_leitura(30.0))
    assert d.avaliar(_leitura(20.0)) == []      # volta pra dentro: zera
    assert d.avaliar(_leitura(30.0)) == []      # recomeça do 1
    assert d.avaliar(_leitura(30.0)) == []
    assert len(d.avaliar(_leitura(30.0))) == 1  # agora sim (3 seguidas)


def test_suspeito_nao_avanca_nem_zera():
    d = _det()
    d.avaliar(_leitura(30.0)); d.avaliar(_leitura(30.0))
    assert d.avaliar(_leitura(0.0, status="suspeito")) == []   # ignora
    eventos = d.avaliar(_leitura(30.0))         # 3ª "ok" fora -> entrada
    assert len(eventos) == 1


def test_saida_so_com_folga():
    d = _det()
    for _ in range(3):
        d.avaliar(_leitura(30.0))               # entra em alarme
    assert d.avaliar(_leitura(24.9)) == []      # dentro do limite mas sem folga (25-0.5=24.5)
    eventos = d.avaliar(_leitura(24.4))         # abaixo de 24.5 -> saida
    assert len(eventos) == 1 and eventos[0]["tipo_evento"] == "saida_alarme"


def test_abaixo_limite():
    d = DetectorAlarme({"S1": {"min": 18.0, "max": 25.0}}, n=1, margem=0.0)
    eventos = d.avaliar(_leitura(10.0))
    assert eventos[0]["tipo_violacao"] == "abaixo_limite"
    assert eventos[0]["limite_min_vigente"] == 18.0


def test_restart_nao_reemite_entrada(tmp_path):
    caminho = str(tmp_path / "estado.json")
    d1 = _det(estado_path=caminho)
    for _ in range(3):
        d1.avaliar(_leitura(30.0))              # entra em alarme, persiste
    d2 = _det(estado_path=caminho)              # "reinicia" carregando estado
    assert d2.avaliar(_leitura(30.0)) == []     # já em alarme -> não re-emite
    eventos = d2.avaliar(_leitura(24.0))        # com folga -> saida
    assert len(eventos) == 1 and eventos[0]["tipo_evento"] == "saida_alarme"


def test_sensor_sem_limite_configurado_ignora():
    d = DetectorAlarme({}, n=1)
    assert d.avaliar(_leitura(999.0)) == []


# --- via de falha de instrumento ---

def _tipos(ev):
    return [(e["tipo_evento"], e["tipo_violacao"]) for e in ev]


def test_falha_sensor_entra_na_primeira_leitura_sem_limite():
    d = DetectorAlarme({}, n=3)
    ev = d.avaliar(_leitura(None, status="falha_sensor"))
    assert _tipos(ev) == [("entrada_alarme", "falha_sensor")]
    assert ev[0]["limite_min_vigente"] is None and ev[0]["limite_max_vigente"] is None
    assert set(ev[0]) == {"sensor_id", "area_id", "tipo_medida", "timestamp", "tipo_evento",
                          "tipo_violacao", "valor", "limite_min_vigente", "limite_max_vigente"}


def test_sensor_offline_entra_so_na_terceira_seguida():
    d = DetectorAlarme({}, n=3)
    off = lambda: d.avaliar(_leitura(None, status="sensor_offline"))
    assert off() == [] and off() == []
    assert d.avaliar(_leitura(20.0)) == []      # ok zera
    assert off() == [] and off() == []
    assert _tipos(off()) == [("entrada_alarme", "sensor_offline")]


def test_saida_falha_apos_tres_ok_seguidas():
    d = _det()
    d.avaliar(_leitura(None, status="falha_sensor"))
    assert d.avaliar(_leitura(20.0)) == []
    assert d.avaliar(_leitura(20.0)) == []
    ev = d.avaliar(_leitura(20.0))
    assert _tipos(ev) == [("saida_alarme", "falha_sensor")]
    assert ev[0]["limite_max_vigente"] == 25.0


def test_ok_interrompida_por_falha_reinicia_saida():
    d = DetectorAlarme({}, n=3)
    d.avaliar(_leitura(None, status="falha_sensor"))
    d.avaliar(_leitura(1.0)); d.avaliar(_leitura(1.0))
    assert d.avaliar(_leitura(None, status="falha_sensor")) == []
    d.avaliar(_leitura(1.0)); d.avaliar(_leitura(1.0))
    assert _tipos(d.avaliar(_leitura(1.0))) == [("saida_alarme", "falha_sensor")]


def test_falha_fecha_alarme_de_faixa_aberto_e_abre_falha():
    d = _det()
    for _ in range(3):
        d.avaliar(_leitura(30.0))
    ev = d.avaliar(_leitura(None, status="falha_sensor"))
    assert _tipos(ev) == [("saida_alarme", "acima_limite"), ("entrada_alarme", "falha_sensor")]


def test_troca_falha_offline_com_alarme_aberto_nao_emite():
    d = DetectorAlarme({}, n=3)
    d.avaliar(_leitura(None, status="falha_sensor"))
    for _ in range(3):
        assert d.avaliar(_leitura(None, status="sensor_offline")) == []
    assert d.avaliar(_leitura(None, status="falha_sensor")) == []


def test_apos_recuperar_faixa_reavalia_com_histerese():
    d = _det()
    d.avaliar(_leitura(None, status="falha_sensor"))
    for _ in range(2):
        assert d.avaliar(_leitura(20.0)) == []
    assert _tipos(d.avaliar(_leitura(20.0))) == [("saida_alarme", "falha_sensor")]
    assert d.avaliar(_leitura(30.0)) == []
    assert d.avaliar(_leitura(30.0)) == []
    assert _tipos(d.avaliar(_leitura(30.0))) == [("entrada_alarme", "acima_limite")]


def test_erro_leitura_e_suspeito_nao_alarmam():
    d = _det()
    for _ in range(5):
        assert d.avaliar(_leitura(None, status="erro_leitura")) == []
        assert d.avaliar(_leitura(99.0, status="suspeito")) == []


def test_estado_de_falha_persiste_entre_instancias(tmp_path):
    p = tmp_path / "estado.json"
    d = DetectorAlarme({}, n=3, estado_path=str(p))
    assert len(d.avaliar(_leitura(None, status="falha_sensor"))) == 1
    d2 = DetectorAlarme({}, n=3, estado_path=str(p))
    assert d2.avaliar(_leitura(None, status="falha_sensor")) == []


def test_estado_antigo_sem_chaves_novas_carrega(tmp_path):
    p = tmp_path / "estado.json"
    p.write_text(json.dumps({"S1": {"em_alarme": False, "tipo_violacao": None, "contador": 0}}))
    d = DetectorAlarme({}, n=3, estado_path=str(p))
    assert _tipos(d.avaliar(_leitura(None, status="falha_sensor"))) == [("entrada_alarme", "falha_sensor")]
