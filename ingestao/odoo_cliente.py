import xmlrpc.client


class ClienteOdoo:
    def __init__(self, url, db, usuario, senha, uid, models):
        self.url = url
        self.db = db
        self.senha = senha
        self.uid = uid
        self.models = models


def conectar(url, db, usuario, senha):
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, usuario, senha, {})
    if not uid:
        raise RuntimeError(f"autenticação falhou para usuário '{usuario}' no banco '{db}'")
    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
    return ClienteOdoo(url, db, usuario, senha, uid, models)


def executar(cliente, model, metodo, *args, **kwargs):
    return cliente.models.execute_kw(
        cliente.db, cliente.uid, cliente.senha, model, metodo, list(args), kwargs,
    )


def resolver_coletor(cliente, coletor_code):
    coletores = executar(
        cliente, 'sensor_monitor.coletor', 'search_read',
        [('coletor_code', '=', coletor_code)], fields=['id', 'hub_id'],
    )
    if not coletores:
        raise ValueError(f"coletor '{coletor_code}' não encontrado no Odoo")
    coletor = coletores[0]
    hub_id = coletor['hub_id'][0]
    hubs = executar(cliente, 'sensor_monitor.hub', 'read', [hub_id], fields=['site_id'])
    site_id = hubs[0]['site_id'][0]
    sites = executar(cliente, 'sensor_monitor.site', 'read', [site_id], fields=['site_code'])
    return {
        'id': coletor['id'],
        'hub_id': hub_id,
        'site_id': site_id,
        'site_code': sites[0]['site_code'],
    }
