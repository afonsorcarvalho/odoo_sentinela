import os
import time
import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from ingestao import odoo_cliente

from . import sessions
from .odoo import ODOO_DB, ODOO_URL, get_cliente_servico

SECRET = os.environ.get('API_JWT_SECRET')
if not SECRET:
    raise RuntimeError(
        "API_JWT_SECRET não definido. Defina a variável de ambiente antes de subir a API "
        "(sem isso, tokens JWT usariam um segredo previsível e poderiam ser forjados)."
    )
ALGORITHM = 'HS256'
EXPIRACAO_SEGUNDOS = 3600

router = APIRouter()
_security = HTTPBearer()


class LoginRequest(BaseModel):
    usuario: str
    senha: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'


@router.post('/auth/login', response_model=LoginResponse)
def login(dados: LoginRequest):
    try:
        cliente_usuario = odoo_cliente.conectar(ODOO_URL, ODOO_DB, dados.usuario, dados.senha)
    except RuntimeError:
        raise HTTPException(status_code=401, detail='credenciais inválidas')

    cliente_servico = get_cliente_servico()
    usuarios = odoo_cliente.executar(
        cliente_servico, 'res.users', 'read', [cliente_usuario.uid], fields=['partner_id'],
    )
    partner_id = usuarios[0]['partner_id'][0]

    # `has_group` via XML-RPC execute_kw não aceita a assinatura direta
    # (falha em runtime: "missing 1 required positional argument: 'group_ext_id'").
    # Alternativa equivalente: resolver o xml_id técnico base.group_system
    # (imune a locale, ao contrário de buscar por full_name traduzível) e
    # checar se o uid logado pertence ao grupo correspondente.
    dados_modelo = odoo_cliente.executar(
        cliente_servico, 'ir.model.data', 'search_read',
        [('module', '=', 'base'), ('name', '=', 'group_system')], fields=['res_id'], limit=1,
    )
    is_admin = False
    if dados_modelo:
        usuarios_admin = odoo_cliente.executar(
            cliente_servico, 'res.users', 'search_read',
            [('id', '=', cliente_usuario.uid), ('groups_id', 'in', dados_modelo[0]['res_id'])], fields=['id'],
        )
        is_admin = bool(usuarios_admin)

    jti = uuid.uuid4().hex
    exp = int(time.time()) + EXPIRACAO_SEGUNDOS
    sessions.guardar(jti, cliente_usuario, exp)

    payload = {
        'sub': str(cliente_usuario.uid),
        'partner_id': partner_id,
        'is_admin': is_admin,
        'jti': jti,
        'exp': exp,
    }
    token = jwt.encode(payload, SECRET, algorithm=ALGORITHM)
    return LoginResponse(access_token=token)


def verificar_token(credenciais: HTTPAuthorizationCredentials = Depends(_security)):
    try:
        return jwt.decode(credenciais.credentials, SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail='token inválido ou expirado')


def verificar_token_query(token: str):
    try:
        return jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail='token inválido ou expirado')


def exigir_admin(claims: dict = Depends(verificar_token)):
    if not claims.get('is_admin'):
        raise HTTPException(status_code=403, detail='requer privilégio de administrador')
    return claims


def resolver_cliente_usuario(claims: dict):
    cliente = sessions.obter(claims.get('jti'))
    if cliente is None:
        raise HTTPException(status_code=401, detail='sessão expirada — faça login novamente')
    return cliente


def get_cliente_usuario(claims: dict = Depends(verificar_token)):
    return resolver_cliente_usuario(claims)


def get_cliente_usuario_query(claims: dict = Depends(verificar_token_query)):
    return resolver_cliente_usuario(claims)
