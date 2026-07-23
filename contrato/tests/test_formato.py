import pytest

from contrato import formato


def test_hash_seed_determinismo():
    cab = "# schema_version: 1\n# tipo_arquivo: leituras\n"
    assert formato.hash_seed(cab) == formato.hash_seed(cab)
    assert formato.hash_seed(cab) != formato.hash_seed(cab + "x")


def test_cadeia_hash_encadeia_linhas_e_bate_com_recalculo():
    cab = formato.montar_cabecalho('leituras', 'COL-1', 'HUB-1', 'AA:BB', '2026-07-18', '-03:00', '1.0.0',
                                   'CLI-000123', 'SITE-0001')
    h0 = formato.hash_seed(cab)
    linha1, h1 = formato.gerar_linha_leitura(
        h0, 1, '2026-07-18T00:01:00-03:00', 'SNR-1', 'EXPURGO', 'temperatura', 19.8, 'C', '4-20ma', 'ok',
        1, 1.0, 0.0,
    )
    linha2, h2 = formato.gerar_linha_leitura(
        h1, 2, '2026-07-18T00:02:00-03:00', 'SNR-1', 'EXPURGO', 'temperatura', 19.9, 'C', '4-20ma', 'ok',
        1, 1.0, 0.0,
    )
    assert h1 != h2
    assert linha1.endswith(h1)
    assert linha1.split('|')[0] == '1'
    campos_sem_hash = '1|2026-07-18T00:01:00-03:00|SNR-1|EXPURGO|temperatura|19.8|C|4-20ma|ok|1|1.0000|0.0000'
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


def test_cabecalho_v2_tem_tenant_e_schema_2():
    cab = formato.montar_cabecalho(
        'leituras', 'COL-1', 'HUB-1', '9F:3A', '2026-07-16', '-03:00', '2.3.1',
        'CLI-000123', 'SITE-0001')
    assert '# schema_version: 2' in cab
    assert '# cliente_id: CLI-000123' in cab
    assert '# site_id: SITE-0001' in cab
    # hdr_sig NÃO é montado aqui (é anexado pelo escritor após assinar)
    assert 'hdr_sig' not in cab


def test_cliente_site_validam_identificador():
    import pytest
    with pytest.raises(ValueError):
        formato.montar_cabecalho('leituras', 'COL-1', 'HUB-1', 'fp', '2026-07-16',
                                 '-03:00', '2.3.1', 'CLI|BAD', 'SITE-0001')


def test_linha_leitura_carrega_coeficientes_de_calibracao():
    seed = formato.hash_seed('# cab\n')
    linha, novo_hash = formato.gerar_linha_leitura(
        seed, 1, '2026-07-16T00:01:00-03:00', 'SNR-1', 'EXPURGO', 'temperatura',
        130.60, 'C', '4-20ma', 'ok', 3, 0.965, 0.33)
    campos = linha.split('|')
    # seq|ts|sensor|area|tipo|valor|unidade|proto|status|cert_ver|cal_ganho|cal_offset|hash
    assert campos[9] == '3'
    assert campos[10] == '0.9650'
    assert campos[11] == '0.3300'
    assert campos[-1] == novo_hash
    # hash cobre os coeficientes: recomputar com o mesmo prefixo bate
    sem_hash = '|'.join(campos[:-1])
    assert formato.hash_linha(seed, sem_hash) == novo_hash


def test_validar_segmento_path_aceita_codigo_normal():
    formato.validar_segmento_path("COL-RS485-BUS0")
    formato.validar_segmento_path("HUB-0001")
    formato.validar_segmento_path("CLI-1")


@pytest.mark.parametrize("ruim", ["", ".", "..", "a/b", "a\\b", "../../etc"])
def test_validar_segmento_path_rejeita_traversal(ruim):
    with pytest.raises(ValueError):
        formato.validar_segmento_path(ruim)
