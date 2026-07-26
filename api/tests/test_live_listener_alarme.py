import json

from api import live_listener


def test_receber_alarme_publica_no_live(monkeypatch):
    publicados = []
    monkeypatch.setattr(live_listener.live, 'publicar',
                        lambda sensor_code, payload: publicados.append((sensor_code, payload)))
    payload = json.dumps({"tipo": "alarme_ao_vivo", "sensor_id": "SNR-T-01",
                          "site_id": "SITE-T", "valor": 30.0, "tipo_evento": "entrada_alarme"})
    live_listener._receber_alarme(None, None, 'alarme_ao_vivo', payload)
    assert len(publicados) == 1
    sensor_code, enviado = publicados[0]
    assert sensor_code == "SNR-T-01"
    assert enviado["tipo"] == "alarme_ao_vivo"
    assert enviado["site_id"] == "SITE-T"
