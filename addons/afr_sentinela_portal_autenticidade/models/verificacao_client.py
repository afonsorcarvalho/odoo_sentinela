import requests

from odoo import models


class VerificacaoClient(models.AbstractModel):
    _name = 'sensor_monitor.verificacao.client'
    _description = 'Cliente HTTP do serviço de verificação (api)'

    def _base_url(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'sentinela.api_base_url', 'http://api:8000')

    def _segredo(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'sentinela.portal_verificar_secret', 'dev-portal-secret-trocar')

    def enviar(self, nome, dados, ip):
        resp = requests.post(
            f'{self._base_url()}/verificar',
            files={'arquivo': (nome, dados)},
            headers={'X-Forwarded-For': ip or '', 'X-Portal-Secret': self._segredo()},
            timeout=30)
        resp.raise_for_status()
        return resp.json()

    def status(self, job_id):
        resp = requests.get(
            f'{self._base_url()}/verificar/{job_id}',
            headers={'X-Portal-Secret': self._segredo()},
            timeout=15)
        if resp.status_code == 404:
            return {'estado': 'expirado'}
        resp.raise_for_status()
        return resp.json()
