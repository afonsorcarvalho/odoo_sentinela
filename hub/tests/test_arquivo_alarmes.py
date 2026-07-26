from datetime import date, datetime, timezone

from cryptography.hazmat.primitives.serialization import load_pem_public_key

from hub.arquivo_alarmes import ArquivoAlarmes
from hub.assinador import AssinadorSoftware
from ingestao import validador


def _assinador(tmp_path):
    return AssinadorSoftware(str(tmp_path / "chave.pem"))  # cria se não existe


def _pubkey(ass):
    return load_pem_public_key(ass.chave_publica_pem().encode())


def _evento(valor, tipo_evento, tipo_violacao):
    return {"sensor_id": "SNR-T-01", "area_id": "AREA-T", "tipo_medida": "temperatura",
            "timestamp": datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc),
            "tipo_evento": tipo_evento, "tipo_violacao": tipo_violacao, "valor": valor,
            "limite_min_vigente": 18.0, "limite_max_vigente": 25.0}


def test_arquivo_alarmes_valido_para_o_validador(tmp_path):
    ass = _assinador(tmp_path)
    arq = ArquivoAlarmes("COL-T", "HUB-T", "0.1.0", "-03:00", str(tmp_path / "dados"), ass,
                         cliente_id="CLI-T", site_id="SITE-T")
    arq.registrar_evento(_evento(30.0, "entrada_alarme", "acima_limite"))
    arq.registrar_evento(_evento(24.0, "saida_alarme", "acima_limite"))
    arq.selar("2026-07-26")

    conteudo = arq.caminho("2026-07-26").read_text()
    resultado = validador.validar_texto(conteudo, _pubkey(ass))
    assert resultado.status_validacao == "valido", resultado.motivo_rejeicao
    assert resultado.tipo_arquivo == "alarmes"
    assert resultado.total_linhas == 2


def test_recuperar_pendentes_sela_dia_anterior(tmp_path):
    ass = _assinador(tmp_path)
    arq = ArquivoAlarmes("COL-T", "HUB-T", "0.1.0", "-03:00", str(tmp_path / "dados"), ass)
    ev = _evento(30.0, "entrada_alarme", "acima_limite")
    ev["timestamp"] = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)
    arq.registrar_evento(ev)
    arq2 = ArquivoAlarmes("COL-T", "HUB-T", "0.1.0", "-03:00", str(tmp_path / "dados"), ass)
    arq2.recuperar_pendentes(date(2026, 7, 26))
    from hub.arquivo_diario import _esta_selado
    assert _esta_selado(arq2.caminho("2026-07-25"))
