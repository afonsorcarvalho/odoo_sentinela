from odoo import api, fields, models

from .common import validate_code


class Coletor(models.Model):
    _name = 'sensor_monitor.coletor'
    _description = 'Coletor'

    name = fields.Char(required=True)
    hub_id = fields.Many2one('sensor_monitor.hub', required=True)
    coletor_code = fields.Char(required=True)
    tipo = fields.Selection([
        ('esp32_wifi', 'ESP32 WiFi'),
        ('esp32_ethernet', 'ESP32 Ethernet'),
        ('esp32_rs485_externo', 'ESP32 RS-485 Externo'),
        ('hub_rs485_embutido', 'Hub RS-485 Embutido'),
    ], required=True)
    is_hub_embutido = fields.Boolean(compute='_compute_is_hub_embutido', store=True)
    hardware_modelo = fields.Char()
    pubkey_fingerprint = fields.Char()
    firmware_version = fields.Char()
    status = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline'),
    ], default='offline', required=True)
    ultimo_arquivo_recebido = fields.Datetime()
    config_version_desejada = fields.Integer(default=1)
    config_version_aplicada = fields.Integer(default=0)
    config_version_reportada_em = fields.Datetime()

    _sql_constraints = [
        ('coletor_code_unique', 'unique(coletor_code)', 'Código de coletor já cadastrado.'),
    ]

    @api.depends('tipo')
    def _compute_is_hub_embutido(self):
        for coletor in self:
            coletor.is_hub_embutido = coletor.tipo == 'hub_rs485_embutido'

    @api.constrains('coletor_code')
    def _check_coletor_code(self):
        for coletor in self:
            validate_code(coletor.coletor_code)
