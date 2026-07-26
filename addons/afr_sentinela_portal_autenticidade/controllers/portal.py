from odoo import http
from odoo.http import request


def _client():
    return request.env['sensor_monitor.verificacao.client'].sudo()


def _ip():
    xff = request.httprequest.headers.get('X-Forwarded-For', '')
    return xff.split(',')[0].strip() if xff else request.httprequest.remote_addr


class PortalAutenticidade(http.Controller):

    @http.route('/verificar-autenticidade', type='http', auth='public',
                website=True, methods=['GET'], csrf=False)
    def form(self, **kw):
        return request.render('afr_sentinela_portal_autenticidade.form', {'erro': False})

    @http.route('/verificar-autenticidade', type='http', auth='public',
                website=True, methods=['POST'], csrf=False)
    def enviar(self, arquivo=None, **kw):
        if arquivo is None:
            return request.render('afr_sentinela_portal_autenticidade.form',
                                  {'erro': 'Selecione um arquivo.'})
        dados = arquivo.read()
        try:
            r = _client().enviar(arquivo.filename, dados, _ip())
        except Exception:
            return request.render('afr_sentinela_portal_autenticidade.form',
                                  {'erro': 'Servidor ocupado, tente novamente em instantes.'})
        return request.render('afr_sentinela_portal_autenticidade.processando',
                              {'job_id': r['job_id'], 'posicao': r.get('posicao', 0)})

    @http.route('/verificar-autenticidade/<job_id>', type='http', auth='public',
                website=True, methods=['GET'], csrf=False)
    def status(self, job_id, **kw):
        s = _client().status(job_id)
        # No Stage 5 este método passa a renderizar o relatório quando pronto.
        return request.make_json_response(s)
