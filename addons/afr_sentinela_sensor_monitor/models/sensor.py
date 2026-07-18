from odoo import api, fields, models

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

    _sql_constraints = [
        ('sensor_code_unique', 'unique(sensor_code)', 'Código de sensor já cadastrado.'),
    ]

    @api.constrains('sensor_code')
    def _check_sensor_code(self):
        for sensor in self:
            validate_code(sensor.sensor_code)
