import pytest

from contrato import formato


def test_hash_seed_determinismo():
    cab = "# schema_version: 1\n# tipo_arquivo: leituras\n"
    assert formato.hash_seed(cab) == formato.hash_seed(cab)
    assert formato.hash_seed(cab) != formato.hash_seed(cab + "x")


def test_cadeia_hash_encadeia_linhas_e_bate_com_recalculo():
    cab = formato.montar_cabecalho('leituras', 'COL-1', 'HUB-1', 'AA:BB', '2026-07-18', '-03:00', '1.0.0')
    h0 = formato.hash_seed(cab)
    linha1, h1 = formato.gerar_linha_leitura(
        h0, 1, '2026-07-18T00:01:00-03:00', 'SNR-1', 'EXPURGO', 'temperatura', 19.8, 'C', '4-20ma', 'ok',
    )
    linha2, h2 = formato.gerar_linha_leitura(
        h1, 2, '2026-07-18T00:02:00-03:00', 'SNR-1', 'EXPURGO', 'temperatura', 19.9, 'C', '4-20ma', 'ok',
    )
    assert h1 != h2
    assert linha1.endswith(h1)
    assert linha1.split('|')[0] == '1'
    campos_sem_hash = '1|2026-07-18T00:01:00-03:00|SNR-1|EXPURGO|temperatura|19.8|C|4-20ma|ok'
    assert formato.hash_linha(h0, campos_sem_hash) == h1


def test_validar_identificador_rejeita_caracteres_proibidos():
    with pytest.raises(ValueError):
        formato.validar_identificador('SNR|001')
    with pytest.raises(ValueError):
        formato.validar_identificador('SNR\n001')
    with pytest.raises(ValueError):
        formato.validar_identificador('SNR\r001')
    formato.validar_identificador('SNR-001')  # não levanta


def test_linha_alarme_usa_travessao_quando_limite_ausente():
    linha, h = formato.gerar_linha_alarme(
        'seed', 1, '2026-07-18T02:00:00-03:00', 'SNR-PRES', 'EXPURGO', 'pressao_diferencial',
        'entrada_alarme', 'acima_limite', 1.0, None, -2.5,
    )
    campos = linha.split('|')
    assert campos[8] == '—'
    assert campos[9] == '-2.5'


def test_montar_rodape_leituras():
    rodape = formato.montar_rodape(2880, 'abc123', 'ZmFrZQ==', 'total_linhas')
    assert '# total_linhas: 2880' in rodape
    assert '# hash_final: abc123' in rodape
    assert '# assinatura: ZmFrZQ==' in rodape
