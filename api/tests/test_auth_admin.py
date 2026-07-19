from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def _login(usuario, senha):
    return client.post('/auth/login', json={'usuario': usuario, 'senha': senha})


def test_login_admin_tem_claim_is_admin_true():
    import jwt as _jwt
    from api.auth import SECRET, ALGORITHM

    resp = _login('admin', 'admin')
    assert resp.status_code == 200
    token = resp.json()['access_token']
    claims = _jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    assert claims.get('is_admin') is True


def test_exigir_admin_bloqueia_nao_admin():
    import pytest
    from fastapi import HTTPException
    from api.auth import exigir_admin

    with pytest.raises(HTTPException) as exc:
        exigir_admin({'is_admin': False})
    assert exc.value.status_code == 403


def test_exigir_admin_permite_admin():
    from api.auth import exigir_admin

    claims = {'is_admin': True, 'sub': '2'}
    assert exigir_admin(claims) == claims
