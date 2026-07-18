from odoo import api, fields, models

from .common import validate_code


class Hub(models.Model):
    _name = 'sensor_monitor.hub'
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

    _sql_constraints = [
        ('hub_code_unique', 'unique(hub_code)', 'Código de hub já cadastrado.'),
    ]

    @api.constrains('hub_code')
    def _check_hub_code(self):
        for hub in self:
            validate_code(hub.hub_code)
