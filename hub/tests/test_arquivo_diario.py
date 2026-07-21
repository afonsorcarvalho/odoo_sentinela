from datetime import date, datetime, timedelta, timezone

from hub.arquivo_diario import ArquivoDiario
from hub.assinador import AssinadorSoftware

TZ = timezone(timedelta(hours=-3))


def _leitura(dt, valor=19.8, sensor="SNR-EXP-TEMP-01"):
    return {
        "timestamp": dt, "sensor_id": sensor, "area_id": "AREA-EXPURGO",
        "tipo_medida": "temperatura", "valor": valor, "unidade": "C",
        "protocolo_origem": "4-20ma", "status_leitura": "ok",
    }


def _fazer(tmp_path):
    ass = AssinadorSoftware(tmp_path / "k.pem")
    arq = ArquivoDiario("COL-RS485-BUS0", "HUB-0001", "0.1.0", "-03:00",
                        tmp_path / "dados", ass)
    return arq, ass


def test_registrar_cria_cabecalho_e_linha(tmp_path):
    arq, _ = _fazer(tmp_path)
    dt = datetime(2026, 7, 21, 0, 1, tzinfo=TZ)
    arq.registrar(_leitura(dt))
    texto = arq.caminho("2026-07-21").read_text()
    assert "# coletor_id: COL-RS485-BUS0" in texto
    assert "SNR-EXP-TEMP-01|AREA-EXPURGO|temperatura|19.8|C|4-20ma|ok|" in texto


def test_selar_adiciona_rodape_com_assinatura(tmp_path):
    arq, _ = _fazer(tmp_path)
    dt = datetime(2026, 7, 21, 0, 1, tzinfo=TZ)
    arq.registrar(_leitura(dt))
    arq.selar("2026-07-21")
    texto = arq.caminho("2026-07-21").read_text()
    assert "# hash_final: " in texto
    assert "# assinatura: " in texto


def test_virada_de_dia_sela_o_anterior(tmp_path):
    arq, _ = _fazer(tmp_path)
    arq.registrar(_leitura(datetime(2026, 7, 21, 23, 59, tzinfo=TZ)))
    arq.registrar(_leitura(datetime(2026, 7, 22, 0, 1, tzinfo=TZ)))
    ontem = arq.caminho("2026-07-21").read_text()
    hoje = arq.caminho("2026-07-22").read_text()
    assert "# assinatura: " in ontem          # dia anterior foi selado
    assert "# assinatura: " not in hoje        # dia corrente ainda aberto


def test_recuperar_pendentes_sela_dia_passado(tmp_path):
    arq, _ = _fazer(tmp_path)
    arq.registrar(_leitura(datetime(2026, 7, 20, 10, 0, tzinfo=TZ)))
    # simula crash: não selou. Nova instância recupera.
    arq2, _ = _fazer(tmp_path)
    arq2.recuperar_pendentes(date(2026, 7, 21))
    texto = arq2.caminho("2026-07-20").read_text()
    assert "# assinatura: " in texto
