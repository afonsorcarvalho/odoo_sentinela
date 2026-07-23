from odoo import api, fields, models

from .calibracao import CONVERSOR_TIPOS
from .common import validate_code


class Sensor(models.Model):
    _name = 'sensor_monitor.sensor'
    _description = 'Sensor'

    name = fields.Char(required=True)
    sensor_code = fields.Char(required=True)
    coletor_id = fields.Many2one('sensor_monitor.coletor', required=True)
    area_id = fields.Many2one('sensor_monitor.area', required=True)
    measurement_type_id = fields.Many2one('sensor_monitor.measurement.type', required=True)
    protocolo_origem = fields.Selection([
        ('4-20ma', '4-20mA'),
        ('rs485', 'RS-485'),
        ('i2c', 'I2C'),
    ], required=True)
    unidade = fields.Char()
    ativo = fields.Boolean(default=True)
    conversor_tipo = fields.Selection(
        CONVERSOR_TIPOS, default='nenhum', required=True,
        help='Conversor da malha (atributo, não peça rastreada). "Nenhum" = o sensor '
             'entrega o valor direto. Trocar o conversor invalida a calibração vigente.')
    calibracao_ids = fields.One2many(
        'sensor_monitor.calibracao', 'sensor_id', string='Certificados de Calibração')
    calibracao_vigente_id = fields.Many2one(
        'sensor_monitor.calibracao', compute='_compute_calibracao_vigente', store=False,
        help='Certificado cuja janela contém hoje E cujo conversor casa com o atual.')

    _sql_constraints = [
        ('sensor_code_unique', 'unique(sensor_code)', 'Código de sensor já cadastrado.'),
    ]

    @api.constrains('sensor_code')
    def _check_sensor_code(self):
        for sensor in self:
            validate_code(sensor.sensor_code)

    @api.depends('conversor_tipo', 'calibracao_ids.validade_de',
                 'calibracao_ids.validade_ate', 'calibracao_ids.conversor_tipo_snapshot',
                 'calibracao_ids.versao')
    def _compute_calibracao_vigente(self):
        hoje = fields.Date.context_today(self)
        for sensor in self:
            candidatos = sensor.calibracao_ids.filtered(
                lambda c: c.conversor_tipo_snapshot == sensor.conversor_tipo
                and c.validade_de and c.validade_ate
                and c.validade_de <= hoje <= c.validade_ate)
            sensor.calibracao_vigente_id = (
                max(candidatos, key=lambda c: c.versao) if candidatos else False)
