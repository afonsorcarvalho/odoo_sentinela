from datetime import date

from werkzeug.wrappers import Response

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request


class SentinelaArquivos(http.Controller):

    @http.route('/sentinela/arquivos/zip', type='http', auth='user', methods=['GET'])
    def zip_do_dia(self, site_id=None, data=None, **kw):
        try:
            dia = date.fromisoformat(data or '')
            site_id = int(site_id)
            # id do Postgres é sempre positivo e cabe num integer (int4); fora
            # disso o search() estoura NumericValueOutOfRange lá dentro do
            # client, o que escaparia dos except abaixo e viraria 500.
            if not (1 <= site_id <= 2147483647):
                raise ValueError('site_id fora do intervalo válido.')
        except (TypeError, ValueError):
            return Response(
                'Parâmetros inválidos.', status=400,
                content_type='text/plain; charset=utf-8')
        try:
            # NUNCA .sudo() aqui. arquivo.client.resolver_site usa search()
            # sem sudo de propósito: é o ir.rule rule_site_tenant, aplicado
            # sobre o usuário desta request, quem decide se site_id pertence
            # a este cliente. Essa única linha é todo o isolamento
            # multi-tenant da rota — não tem teste unitário que pegue um
            # sudo() introduzido aqui por engano, só o comportamento em
            # produção. Um futuro debugging de AccessError vai ser tentado
            # a "resolver" adicionando sudo(); não faça isso.
            nome, blocos = request.env['sensor_monitor.arquivo.client'].baixar_zip(site_id, dia)
        except AccessError:
            return Response(
                'Sem acesso a este site.', status=403,
                content_type='text/plain; charset=utf-8')
        except UserError as e:
            # Mensagem já é legível (vem do client); 409 evita que o browser
            # trate como erro genérico de servidor.
            return Response(str(e), status=409, content_type='text/plain; charset=utf-8')
        # Streaming: o ZIP inteiro nunca fica em memória neste processo.
        return Response(
            blocos, status=200, content_type='application/zip',
            headers=[('Content-Disposition', f'attachment; filename="{nome}"')])
