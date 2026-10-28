from datetime import datetime, timezone

from ingestao import odoo_cliente

from .alarmes import _CAMPOS_EVENTO, _para_string_odoo, _serializar_evento

_CAMPOS_LIMITE = ('limite_min', 'limite_max')


def alarmes_periodo(cliente, sensor_code, inicio_utc, fim_utc):
    """Alarmes do sensor que se sobrepõem a [inicio, fim): detectados antes do fim e
    ainda abertos ou resolvidos a partir do início. Sem limite, ordenados por detecção."""
    sensor_ids = odoo_cliente.executar(
        cliente, 'sensor_monitor.sensor', 'search', [('sensor_code', '=', sensor_code)],
    )
    if not sensor_ids:
        raise ValueError(f"sensor '{sensor_code}' não encontrado")
    dominio = [
        ('sensor_id', '=', sensor_ids[0]),
        ('timestamp_deteccao', '<', _para_string_odoo(fim_utc)),
        '|',
        ('timestamp_resolucao_sensor', '=', False),
        ('timestamp_resolucao_sensor', '>=', _para_string_odoo(inicio_utc)),
    ]
    eventos = odoo_cliente.executar(
        cliente, 'sensor_monitor.alarm.event', 'search_read', dominio,
        fields=_CAMPOS_EVENTO, order='timestamp_deteccao asc',
    )
    if not eventos:
        return []
    area_ids = list({e['area_id'][0] for e in eventos})
    areas = odoo_cliente.executar(
        cliente, 'sensor_monitor.area', 'read', area_ids, fields=['area_code'],
    )
    sensores_por_id = {sensor_ids[0]: {'sensor_code': sensor_code}}
    areas_por_id = {a['id']: a for a in areas}
    return [_serializar_evento(e, sensores_por_id, areas_por_id) for e in eventos]


def alteracoes_limite(cliente, sensor_code, desde_utc):
    """Alterações de limite_min/limite_max do threshold do sensor feitas a partir de
    `desde_utc`, lidas do histórico de tracking do Odoo, em ordem cronológica."""
    sensor_ids = odoo_cliente.executar(
        cliente, 'sensor_monitor.sensor', 'search', [('sensor_code', '=', sensor_code)],
    )
    if not sensor_ids:
        raise ValueError(f"sensor '{sensor_code}' não encontrado")
    threshold_ids = odoo_cliente.executar(
        cliente, 'sensor_monitor.alarm.threshold', 'search', [('sensor_id', '=', sensor_ids[0])],
    )
    if not threshold_ids:
        return []
    mensagens = odoo_cliente.executar(
        cliente, 'mail.message', 'search_read',
        [
            ('model', '=', 'sensor_monitor.alarm.threshold'),
            ('res_id', 'in', threshold_ids),
            ('date', '>=', _para_string_odoo(desde_utc)),
            ('tracking_value_ids', '!=', False),
        ],
        fields=['date'],
    )
    if not mensagens:
        return []
    data_por_mensagem = {m['id']: m['date'] for m in mensagens}
    valores = odoo_cliente.executar(
        cliente, 'mail.tracking.value', 'search_read',
        [('mail_message_id', 'in', list(data_por_mensagem))],
        fields=['mail_message_id', 'field_id', 'old_value_float', 'new_value_float'],
    )
    # field_id é many2one para ir.model.fields; o nome técnico vem de uma leitura à parte.
    campo_ids = list({v['field_id'][0] for v in valores if v['field_id']})
    campos = odoo_cliente.executar(
        cliente, 'ir.model.fields', 'read', campo_ids, fields=['name'],
    ) if campo_ids else []
    nome_por_campo = {c['id']: c['name'] for c in campos}

    alteracoes = []
    for v in valores:
        campo = nome_por_campo.get(v['field_id'][0]) if v['field_id'] else None
        if campo not in _CAMPOS_LIMITE:
            continue
        quando = datetime.strptime(
            data_por_mensagem[v['mail_message_id'][0]], '%Y-%m-%d %H:%M:%S',
        ).replace(tzinfo=timezone.utc)
        alteracoes.append({
            'quando': quando,
            'campo': campo,
            'de': float(v['old_value_float']),
            'para': float(v['new_value_float']),
        })
    alteracoes.sort(key=lambda a: (a['quando'], a['campo']))
    return alteracoes


def nome_emissor(cliente):
    usuario = odoo_cliente.executar(
        cliente, 'res.users', 'read', [cliente.uid], fields=['name', 'login'],
    )[0]
    return f"{usuario['name']} ({usuario['login']})"
