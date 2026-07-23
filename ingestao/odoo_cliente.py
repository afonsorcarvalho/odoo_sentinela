import threading
import xmlrpc.client
from datetime import datetime, timezone

_lock = threading.Lock()


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
    with _lock:
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
    sites = executar(cliente, 'sensor_monitor.site', 'read', [site_id],
                     fields=['site_code', 'partner_id'])
    partner_id = sites[0]['partner_id'][0]
    partner = executar(cliente, 'res.partner', 'read', [partner_id], fields=['ref'])[0]
    cliente_id = partner.get('ref') or f"CLI-{partner_id}"
    return {
        'id': coletor['id'],
        'hub_id': hub_id,
        'site_id': site_id,
        'site_code': sites[0]['site_code'],
        'cliente_id': cliente_id,
    }


def escrever_ledger(cliente, coletor_odoo_id, tipo_arquivo, data_referencia, status_validacao,
                     motivo_rejeicao, total_linhas, hash_final, assinatura):
    existentes = executar(
        cliente, 'sensor_monitor.file.ledger', 'search',
        [
            ('coletor_id', '=', coletor_odoo_id),
            ('data_referencia', '=', data_referencia),
            ('tipo_arquivo', '=', tipo_arquivo),
        ],
    )
    valores = {
        'coletor_id': coletor_odoo_id,
        'tipo_arquivo': tipo_arquivo,
        'data_referencia': data_referencia,
        'status_validacao': status_validacao,
        'motivo_rejeicao': motivo_rejeicao or False,
        'total_linhas': total_linhas,
        'hash_final': hash_final or False,
        'assinatura': assinatura or False,
        'horario_recebimento': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
    }
    if existentes:
        executar(cliente, 'sensor_monitor.file.ledger', 'write', existentes, valores)
        return existentes[0]
    return executar(cliente, 'sensor_monitor.file.ledger', 'create', valores)


def _timestamp_arquivo_para_utc(timestamp_iso):
    dt = datetime.fromisoformat(timestamp_iso)
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def resolver_sensor(cliente, sensor_code):
    sensores = executar(
        cliente, 'sensor_monitor.sensor', 'search_read',
        [('sensor_code', '=', sensor_code)], fields=['id', 'area_id'],
    )
    if not sensores:
        raise ValueError(f"sensor '{sensor_code}' não encontrado no Odoo")
    sensor = sensores[0]
    return {'id': sensor['id'], 'area_id': sensor['area_id'][0]}


def processar_entrada_alarme(cliente, evento, sensor_odoo_id, area_odoo_id, coletor_odoo_id, hash_arquivo):
    if evento['tipo_violacao'] == 'acima_limite':
        limite_snapshot = evento['limite_max_vigente']
    elif evento['tipo_violacao'] == 'abaixo_limite':
        limite_snapshot = evento['limite_min_vigente']
    else:
        limite_snapshot = None
    valores = {
        'sensor_id': sensor_odoo_id,
        'area_id': area_odoo_id,
        'coletor_id': coletor_odoo_id,
        'timestamp_deteccao': _timestamp_arquivo_para_utc(evento['timestamp']),
        'valor_lido': evento['valor'],
        'tipo_violacao': evento['tipo_violacao'],
        'limite_configurado_snapshot': limite_snapshot if limite_snapshot is not None else 0.0,
        'origem_arquivo_hash': hash_arquivo or False,
        'status': 'aberto',
    }
    return executar(cliente, 'sensor_monitor.alarm.event', 'create', valores)


def processar_saida_alarme(cliente, evento, sensor_odoo_id):
    abertos = executar(
        cliente, 'sensor_monitor.alarm.event', 'search',
        [
            ('sensor_id', '=', sensor_odoo_id),
            ('timestamp_resolucao_sensor', '=', False),
        ],
        order='timestamp_deteccao desc', limit=1,
    )
    if not abertos:
        return None
    executar(
        cliente, 'sensor_monitor.alarm.event', 'write', abertos,
        {'timestamp_resolucao_sensor': _timestamp_arquivo_para_utc(evento['timestamp'])},
    )
    return abertos[0]
