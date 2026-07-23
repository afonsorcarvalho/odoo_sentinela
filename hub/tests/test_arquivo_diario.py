from datetime import date, datetime, timedelta, timezone

import pytest

from hub.arquivo_diario import ArquivoDiario
from hub.assinador import AssinadorSoftware

TZ = timezone(timedelta(hours=-3))


@pytest.fixture
def assinador(tmp_path):
    return AssinadorSoftware(str(tmp_path / "chave.pem"))


def _leitura(dt, valor=19.8, sensor="SNR-EXP-TEMP-01"):
    return {
        "timestamp": dt, "sensor_id": sensor, "area_id": "AREA-EXPURGO",
        "tipo_medida": "temperatura", "valor": valor, "unidade": "C",
        "protocolo_origem": "4-20ma", "status_leitura": "ok",
        "cert_ver": 3, "cal_ganho": 0.965, "cal_offset": 0.33,
    }


def _fazer(tmp_path, ass=None):
    ass = ass or AssinadorSoftware(tmp_path / "k.pem")
    arq = ArquivoDiario("COL-RS485-BUS0", "HUB-0001", "0.1.0", "-03:00",
                        tmp_path / "dados", ass, cliente_id="CLI-1", site_id="SITE-1")
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


def test_caminho_tem_nome_auto_descritivo(tmp_path):
    arq, _ = _fazer(tmp_path)
    caminho = arq.caminho("2026-07-21")
    assert caminho.name == "2026-07-21_HUB-0001-COL-RS485-BUS0_leituras.txt"


def test_recuperar_pendentes_sela_arquivo_com_nome_legado(tmp_path):
    """FIX C2: recuperar_pendentes acha o arquivo pelo nome REAL em disco, mas
    selar reconstruía o caminho via self.caminho(data) — que gera o nome NOVO.
    Num arquivo em campo com o nome legado ({data}_leituras.txt), caminho.exists()
    era falso e selar dava `return` silencioso: o arquivo nunca é selado, nunca
    passa no _esta_selado do EnviadorSftp e nunca sobe — perda muda de dados
    assinados, exatamente no cenário (crash/kill -9) para o qual
    recuperar_pendentes existe."""
    arq, ass = _fazer(tmp_path)
    arq.registrar(_leitura(datetime(2026, 7, 22, 8, 0, tzinfo=TZ)))
    # renomeia para o formato legado: simula arquivo gravado por versão anterior
    # que ficou sem rodapé (crash antes de selar).
    novo = arq.caminho("2026-07-22")
    legado = novo.parent / "2026-07-22_leituras.txt"
    novo.rename(legado)
    assert "# assinatura:" not in legado.read_text()

    arq2, _ = _fazer(tmp_path, ass=ass)
    arq2.recuperar_pendentes(date(2026, 7, 23))

    assert "# assinatura:" in legado.read_text()   # o arquivo ACHADO foi selado
    assert not novo.exists()                       # e nada foi criado no nome novo


def test_arquivo_v2_tem_hdr_sig_e_sig_por_linha(tmp_path, assinador):
    from hub.arquivo_diario import ArquivoDiario
    arq = ArquivoDiario('COL-1', 'HUB-1', '2.3.1', '-03:00', str(tmp_path), assinador,
                        cliente_id='CLI-1', site_id='SITE-1')
    arq.registrar(_leitura(datetime(2026, 7, 16, 0, 1, 0)))
    arq.registrar(_leitura(datetime(2026, 7, 16, 0, 2, 0)))
    texto = arq.caminho('2026-07-16').read_text()
    linhas = [l for l in texto.split('\n') if l]

    assert '# schema_version: 2' in texto
    assert any(l.startswith('# hdr_sig: ') for l in linhas)

    corpo = [l for l in linhas if not l.startswith('#')]
    assert len(corpo) == 2
    # 14 colunas: ...|cert_ver|cal_ganho|cal_offset|hash|sig
    campos = corpo[0].split('|')
    assert len(campos) == 14
    assert campos[9] == '3' and campos[10] == '0.9650' and campos[11] == '0.3300'
    # cada linha tem sig != vazio
    assert corpo[0].split('|')[-1]
    assert corpo[1].split('|')[-1]


def test_reconstruir_estado_ignora_hdr_sig_e_tira_hash_e_sig(tmp_path, assinador):
    from hub.arquivo_diario import ArquivoDiario, reconstruir_estado
    arq = ArquivoDiario('COL-1', 'HUB-1', '2.3.1', '-03:00', str(tmp_path), assinador,
                        cliente_id='CLI-1', site_id='SITE-1')
    arq.registrar(_leitura(datetime(2026, 7, 16, 0, 1, 0)))
    texto = arq.caminho('2026-07-16').read_text()
    hash_estado, prox_seq = reconstruir_estado(texto)
    # o hash de estado deve casar com o hash da última linha (campo -2)
    corpo = [l for l in texto.split('\n') if l and not l.startswith('#')]
    assert hash_estado == corpo[-1].split('|')[-2]
    assert prox_seq == 2
