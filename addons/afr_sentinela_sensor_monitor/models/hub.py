import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

from .common import validate_code


class Hub(models.Model):
    _name = 'sensor_monitor.hub'
    _inherit = ['mail.thread']
    _description = 'Hub (Raspberry Pi)'

    name = fields.Char(required=True)
    site_id = fields.Many2one('sensor_monitor.site', required=True)
    hub_code = fields.Char(required=True)
    modelo_hardware = fields.Selection([
        ('raspberry_pi_3b', 'Raspberry Pi 3B'),
    ], default='raspberry_pi_3b', required=True)
    openvpn_cert_fingerprint = fields.Char()
    possui_secure_element = fields.Boolean(default=True)
    secure_element_pubkey_fingerprint = fields.Char()
    firmware_version = fields.Char()
    status = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('manutencao', 'Manutenção'),
    ], default='offline', required=True)
    ultimo_contato = fields.Datetime()
    config_version_desejada = fields.Integer(default=1)
    config_version_aplicada = fields.Integer(default=0)
    config_version_reportada_em = fields.Datetime()
    config_em_drift = fields.Boolean(compute='_compute_drift')

    _sql_constraints = [
        ('hub_code_unique', 'unique(hub_code)', 'Código de hub já cadastrado.'),
    ]

    @api.constrains('hub_code')
    def _check_hub_code(self):
        for hub in self:
            validate_code(hub.hub_code)

    @api.depends('config_version_desejada', 'config_version_aplicada')
    def _compute_drift(self):
        for h in self:
            h.config_em_drift = h.config_version_desejada != h.config_version_aplicada

    def action_publicar_config(self):
        self.ensure_one()
        params = self.env['ir.config_parameter'].sudo()
        api_url = params.get_param('sentinela.api_url')
        secret = params.get_param('sentinela.config_publish_secret')
        self.config_version_desejada += 1
        resp = requests.post(
            f'{api_url}/internal/hub/{self.hub_code}/publicar-config',
            headers={'X-Config-Secret': secret}, timeout=15)
        if resp.status_code != 200:
            self.message_post(body=f'Falha ao publicar config: HTTP {resp.status_code}')
            raise UserError('Falha ao publicar configuração (ver chatter).')
        self.message_post(body=f'Configuração v{self.config_version_desejada} publicada.')
