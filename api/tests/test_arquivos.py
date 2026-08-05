from datetime import date

import pytest

from api.arquivos import ParametroInvalido, caminho_do_dia, validar_token


def test_validar_token_aceita_codigos_reais():
    assert validar_token('CLI-43') == 'CLI-43'
    assert validar_token('SITE-DEMO-01') == 'SITE-DEMO-01'
    assert validar_token('HUB_0001A2F3') == 'HUB_0001A2F3'


@pytest.mark.parametrize('valor', [
    '..',
    '../..',
    'a/b',
    'CLI-43/../../etc',
    '%2e%2e',
    'cli 43',
    '',
    'x' * 65,
])
def test_validar_token_recusa_travessia_e_lixo(valor):
    # A defesa contra path traversal mora aqui: se um destes passar, o caminho
    # montado em caminho_do_dia escapa da raiz do acervo.
    with pytest.raises(ParametroInvalido):
        validar_token(valor)


def test_caminho_do_dia_monta_arvore_do_acervo():
    assert caminho_do_dia('/uploads', 'CLI-43', 'SITE-DEMO-01', date(2026, 7, 29)) == \
        '/uploads/CLI-43/2026/07/29/SITE-DEMO-01'


def test_caminho_do_dia_zero_pad_mes_e_dia():
    assert caminho_do_dia('/uploads', 'CLI-1', 'S-1', date(2026, 1, 5)) == \
        '/uploads/CLI-1/2026/01/05/S-1'


def test_caminho_do_dia_valida_os_tokens():
    with pytest.raises(ParametroInvalido):
        caminho_do_dia('/uploads', '../etc', 'S-1', date(2026, 1, 5))
