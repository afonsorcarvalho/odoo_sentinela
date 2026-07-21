from ingestao import odoo_cliente


def obter_sites_permitidos(cliente):
    sites = odoo_cliente.executar(cliente, 'sensor_monitor.site', 'search_read', [], fields=['site_code'])
    return [s['site_code'] for s in sites]
