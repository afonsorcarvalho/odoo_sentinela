from odoo import http
from odoo.http import request


def _client():
    return request.env['sensor_monitor.verificacao.client'].sudo()


def _ip():
    # remote_addr e' o peer TCP; com proxy_mode=True (Odoo atras de proxy
    # confiavel) o werkzeug ProxyFix ja o corrige para o IP real do cliente
    # a partir do X-Forwarded-For do proxy. NAO confiar no header cru aqui:
    # o endpoint e' publico e um cliente direto pode forjar X-Forwarded-For,
    # contornando o rate-limit por IP do api.
    return request.httprequest.remote_addr


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
        max_bytes = 25 * 1024 * 1024
        if (request.httprequest.content_length or 0) > max_bytes:
            return request.render('afr_sentinela_portal_autenticidade.form',
                                  {'erro': 'Arquivo muito grande (máx 25 MB).'})
        dados = arquivo.read()
        try:
            r = _client().enviar(arquivo.filename, dados, _ip())
        except Exception:
            return request.render('afr_sentinela_portal_autenticidade.form',
                                  {'erro': 'Servidor ocupado, tente novamente em instantes.'})
        if not isinstance(r, dict) or not r.get('job_id'):
            return request.render('afr_sentinela_portal_autenticidade.form',
                                  {'erro': 'Resposta inválida do servidor, tente novamente.'})
        return request.render('afr_sentinela_portal_autenticidade.processando',
                              {'job_id': r['job_id'], 'posicao': r.get('posicao', 0)})

    @http.route('/verificar-autenticidade/<job_id>', type='http', auth='public',
                website=True, methods=['GET'], csrf=False)
    def status(self, job_id, **kw):
        try:
            s = _client().status(job_id)
        except Exception:
            s = {'estado': 'indisponivel'}
        if s.get('estado') == 'pronto':
            laudo = request.env['sensor_monitor.verificacao.laudo'].sudo().criar_de_lote(s['lote'])
            return request.render('afr_sentinela_portal_autenticidade.relatorio',
                                  {'laudo': laudo, 'job_id': job_id})
        if request.httprequest.headers.get('Accept', '').startswith('application/json') or kw.get('json'):
            return request.make_json_response(s)
        # ainda processando (ou erro/expirado): página com polling
        return request.render('afr_sentinela_portal_autenticidade.processando',
                              {'job_id': job_id, 'posicao': s.get('posicao', 0)})

    @http.route('/verificar-autenticidade/<job_id>/relatorio.json', type='http',
                auth='public', website=True, methods=['GET'], csrf=False)
    def download_json(self, job_id, **kw):
        try:
            s = _client().status(job_id)
        except Exception:
            s = {'estado': 'indisponivel'}
        return request.make_json_response(s.get('lote', s))

    @http.route('/verificar-autenticidade/<job_id>/laudo.pdf', type='http',
                auth='public', website=True, methods=['GET'], csrf=False)
    def download_pdf(self, job_id, **kw):
        try:
            s = _client().status(job_id)
        except Exception:
            s = {'estado': 'indisponivel'}
        if s.get('estado') != 'pronto':
            return request.not_found()
        laudo = request.env['sensor_monitor.verificacao.laudo'].sudo().criar_de_lote(s['lote'])
        pdf, _ = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'afr_sentinela_portal_autenticidade.laudo', res_ids=laudo.ids)
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', f'attachment; filename="laudo-{job_id}.pdf"')])
