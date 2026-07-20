import os
import subprocess

import pytest
import jwt
from fastapi.testclient import TestClient

from api.auth import ALGORITHM, SECRET
from api.main import app

client = TestClient(app)


def test_login_com_credenciais_validas_retorna_token():
    resposta = client.post('/auth/login', json={'usuario': 'admin', 'senha': 'admin'})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo['token_type'] == 'bearer'
    payload = jwt.decode(corpo['access_token'], SECRET, algorithms=[ALGORITHM])
    assert 'sub' in payload
    assert 'partner_id' in payload
    assert 'exp' in payload


def test_login_com_senha_errada_retorna_401():
    resposta = client.post('/auth/login', json={'usuario': 'admin', 'senha': 'senha_errada_xyz'})
    assert resposta.status_code == 401


def test_auth_falha_ao_subir_sem_api_jwt_secret():
    raiz_repo = subprocess.run(
        ['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True,
    ).stdout.strip()
    env = {k: v for k, v in os.environ.items() if k != 'API_JWT_SECRET'}
    resultado = subprocess.run(
        ['python3', '-c', 'import api.auth'],
        cwd=raiz_repo, env=env, capture_output=True, text=True,
    )
    assert resultado.returncode != 0
    assert 'API_JWT_SECRET' in resultado.stderr


def test_login_inclui_jti_e_permite_obter_cliente_usuario():
    from api.auth import get_cliente_usuario

    resposta = client.post('/auth/login', json={'usuario': 'admin', 'senha': 'admin'})
    corpo = resposta.json()
    payload = jwt.decode(corpo['access_token'], SECRET, algorithms=[ALGORITHM])
    assert 'jti' in payload

    cliente = get_cliente_usuario(payload)
    assert str(cliente.uid) == payload['sub']


def test_get_cliente_usuario_sem_sessao_valida_levanta_401():
    from fastapi import HTTPException

    from api.auth import get_cliente_usuario

    with pytest.raises(HTTPException) as exc:
        get_cliente_usuario({'jti': 'jti-que-nao-existe'})
    assert exc.value.status_code == 401
