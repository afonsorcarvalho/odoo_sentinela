from datetime import datetime, timezone

from cryptography.hazmat.primitives.serialization import load_pem_public_key

from hub.arquivo_alarmes import ArquivoAlarmes
from hub.assinador import AssinadorSoftware
from ingestao import odoo_cliente, validador


def test_alarmes_assinado_falha_sensor_sem_limites_e_ingerido(tmp_path, monkeypatch):
    ass = AssinadorSoftware(str(tmp_path / "chave.pem"))
    arq = ArquivoAlarmes("COL-T", "HUB-T", "0.1.0", "-03:00", str(tmp_path / "dados"), ass,
                         cliente_id="CLI-T", site_id="SITE-T")
    arq.registrar_evento({
        "sensor_id": "SNR-T-01", "area_id": "AREA-T", "tipo_medida": "temperatura",
        "timestamp": datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc),
        "tipo_evento": "entrada_alarme", "tipo_violacao": "falha_sensor", "valor": 0.0,
        "limite_min_vigente": None, "limite_max_vigente": None})
    arq.selar("2026-07-26")
    conteudo = arq.caminho("2026-07-26").read_text()

    rv = validador.validar_texto(conteudo, load_pem_public_key(ass.chave_publica_pem().encode()))
    assert rv.status_validacao == "valido", rv.motivo_rejeicao
    evento = rv.eventos[0]
    assert evento["tipo_violacao"] == "falha_sensor"
    assert evento["limite_min_vigente"] is None and evento["limite_max_vigente"] is None

    criados = []

    def fake_executar(cliente, model, metodo, *args, **kw):
        if metodo == 'search':
            return []
        if metodo == 'create':
            criados.append(args[0])
            return 7
        return []
    monkeypatch.setattr(odoo_cliente, 'executar', fake_executar)
    assert odoo_cliente.processar_entrada_alarme(None, evento, 1, 2, 3, rv.hash_final) == 7
    assert criados[0]['tipo_violacao'] == 'falha_sensor'
    assert criados[0]['limite_configurado_snapshot'] == 0.0
