from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .common import validate_code


class Site(models.Model):
    _name = 'sensor_monitor.site'
    _description = 'Site/Unidade'

    name = fields.Char(required=True)
    partner_id = fields.Many2one('res.partner', required=True, string='Cliente')
    site_code = fields.Char(required=True)
    endereco = fields.Text()
    timezone = fields.Char(default='America/Sao_Paulo')
    vertical = fields.Selection([
        ('cme_hospitalar', 'CME Hospitalar'),
        ('industrial_generico', 'Industrial Genérico'),
    ], required=True)
    ativo = fields.Boolean(default=True)
    retention_mode = fields.Selection([
        ('indefinida', 'Indefinida'),
        ('expurgar_apos', 'Expurgar após período'),
    ], default='indefinida', required=True)
    retention_years = fields.Integer(default=5, required=True)
    lifecycle_status = fields.Selection([
        ('ativo', 'Ativo'),
        ('offboarding', 'Offboarding'),
        ('arquivado', 'Arquivado'),
        ('expurgado', 'Expurgado'),
    ], default='ativo', required=True)
    offboarding_data = fields.Date()
    export_entregue_em = fields.Date()

    _sql_constraints = [
        ('site_code_unique', 'unique(site_code)', 'Código de site já cadastrado.'),
    ]

    @api.constrains('retention_years')
    def _check_retention_years_floor(self):
        for site in self:
            if site.retention_years < 5:
                raise ValidationError('retention_years não pode ser menor que 5 (piso legal RDC 15).')

    @api.constrains('site_code')
    def _check_site_code(self):
        for site in self:
            validate_code(site.site_code)
