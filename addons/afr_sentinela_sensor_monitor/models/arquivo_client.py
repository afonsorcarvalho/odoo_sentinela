import requests

from odoo import models
from odoo.exceptions import AccessError, UserError

# SFTP lento com 60 MB de acervo não pode estourar num timeout de 15 s como o
# do publicar-config; o ZIP costuma levar segundos, mas a margem é barata.
_TIMEOUT = 300


class ArquivoClient(models.AbstractModel):
    _name = 'sensor_monitor.arquivo.client'
    _description = 'Cliente HTTP do acervo de arquivos diários'

    def _base_url(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'sentinela.api_url', 'http://api:8000')

    def _secret(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'sentinela.config_publish_secret', '')

    def resolver_site(self, site_id):
        """Site que o usuário corrente pode ler — sem sudo, de propósito.

        `search` é o que aplica o ir.rule rule_site_tenant: site de outro
        partner simplesmente não aparece no resultado. Usar
        `browse(...).exists()` aqui seria um furo — `exists()` só confere a
        existência da linha no banco e ignora record rule.

        Site inexistente e site alheio dão a mesma resposta, para não vazar
        existência de registro.
        """
        site = self.env['sensor_monitor.site'].search([('id', '=', int(site_id))], limit=1)
        if not site:
            raise AccessError('Site não encontrado ou fora do seu acesso.')
        return site

    def baixar_zip(self, site_id, data):
        """(nome_do_zip, iterador de blocos) para o dia/site pedido."""
        site = self.resolver_site(site_id)
        partner = site.partner_id
        cliente_id = partner.ref or f'CLI-{partner.id}'
        iso = data.isoformat()
        try:
            resp = requests.get(
                f'{self._base_url()}/internal/arquivos/zip',
                params={'cliente': cliente_id, 'site': site.site_code, 'data': iso},
                headers={'X-Config-Secret': self._secret()},
                stream=True, timeout=_TIMEOUT)
        except Exception:
            raise UserError('Serviço de arquivos indisponível. Tente novamente.')
        if resp.status_code == 404:
            raise UserError(
                f'Nenhum arquivo encontrado para {site.site_code} em '
                f'{data.strftime("%d/%m/%Y")}.')
        if resp.status_code == 413:
            raise UserError('Volume acima do limite; escolha um dia com menos coletores.')
        if resp.status_code != 200:
            raise UserError('Serviço de arquivos indisponível. Tente novamente.')
        nome = f'sentinela_{site.site_code}_{iso}.zip'
        return nome, resp.iter_content(64 * 1024)
