from odoo import fields, models


class MeasurementType(models.Model):
    _name = 'sensor_monitor.measurement.type'
    _description = 'Tipo de Medição'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    unidade_padrao = fields.Char(required=True)

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Código já cadastrado.'),
    ]
