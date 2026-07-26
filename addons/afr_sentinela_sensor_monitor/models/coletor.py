import hashlib

from cryptography.hazmat.primitives import serialization

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
    pubkey_pem = fields.Text(help='Chave pública (PEM) do coletor, usada na verificação de autenticidade.')
    pubkey_fingerprint = fields.Char(compute='_compute_pubkey_fingerprint', store=True)
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

    @api.depends('pubkey_pem')
    def _compute_pubkey_fingerprint(self):
        for coletor in self:
            if not coletor.pubkey_pem:
                # Sem PEM (ainda) não significa "sem fingerprint": preserva
                # um valor já armazenado (ex.: cadastrado manualmente antes
                # do coletor enviar a chave) em vez de apagá-lo num -u.
                coletor.pubkey_fingerprint = coletor.pubkey_fingerprint
                continue
            try:
                chave = serialization.load_pem_public_key(coletor.pubkey_pem.encode())
                der = chave.public_bytes(
                    encoding=serialization.Encoding.DER,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                )
                d = hashlib.sha256(der).hexdigest().upper()
                coletor.pubkey_fingerprint = ':'.join(d[i:i + 2] for i in range(0, len(d), 2))
            except (ValueError, TypeError):
                coletor.pubkey_fingerprint = False
