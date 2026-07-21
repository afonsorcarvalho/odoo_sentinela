from unittest import mock

from ingestao import receber_upload


def test_main_chama_ingerir_com_caminho_e_env(monkeypatch):
    monkeypatch.setenv("SENTINELA_REGISTRO", "/reg.json")
    monkeypatch.setenv("SENTINELA_DSN", "postgresql://x")
    with mock.patch("ingestao.receber_upload.odoo_cliente.conectar") as conectar, \
         mock.patch("ingestao.receber_upload.ingestor.ingerir_arquivo") as ingerir:
        cliente = conectar.return_value
        receber_upload.main(["/uploads/2026-07-21_leituras.txt"])
    ingerir.assert_called_once_with("/uploads/2026-07-21_leituras.txt", "/reg.json",
                                    "postgresql://x", cliente)
