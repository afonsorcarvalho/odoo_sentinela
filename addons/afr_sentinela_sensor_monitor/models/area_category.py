from odoo import fields, models


class AreaCategory(models.Model):
    _name = 'sensor_monitor.area.category'
    _description = 'Categoria de Área'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    vertical = fields.Selection([
        ('cme_hospitalar', 'CME Hospitalar'),
        ('industrial_generico', 'Industrial Genérico'),
    ], required=True)

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Código já cadastrado.'),
    ]
