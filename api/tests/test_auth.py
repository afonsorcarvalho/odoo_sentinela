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
