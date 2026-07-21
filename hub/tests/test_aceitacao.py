from datetime import datetime, timedelta, timezone

from hub.arquivo_diario import ArquivoDiario
from hub.assinador import AssinadorSoftware
from ingestao import registro_coletores, validador

TZ = timezone(timedelta(hours=-3))


def _leitura(dt, valor, sensor):
    return {
        "timestamp": dt, "sensor_id": sensor, "area_id": "AREA-EXPURGO",
        "tipo_medida": "temperatura", "valor": valor, "unidade": "C",
        "protocolo_origem": "4-20ma", "status_leitura": "ok",
    }


def test_arquivo_do_hub_e_aceito_pela_ingestao(tmp_path):
    coletor_id = "COL-RS485-BUS0"
    assinador = AssinadorSoftware(tmp_path / "k.pem")
    arq = ArquivoDiario(coletor_id, "HUB-0001", "0.1.0", "-03:00", tmp_path / "dados", assinador)

    base = datetime(2026, 7, 21, 0, 1, tzinfo=TZ)
    for i in range(3):
        arq.registrar(_leitura(base + timedelta(minutes=i), 19.0 + i * 0.1, "SNR-EXP-TEMP-01"))
    arq.selar("2026-07-21")

    registro = tmp_path / "coletores_conhecidos.json"
    registro_coletores.registrar_coletor(registro, coletor_id, assinador.chave_publica_pem())

    resultado = validador.validar_arquivo(arq.caminho("2026-07-21"), registro)
    assert resultado.status_validacao == "valido", resultado.motivo_rejeicao
    assert resultado.total_linhas == 3
