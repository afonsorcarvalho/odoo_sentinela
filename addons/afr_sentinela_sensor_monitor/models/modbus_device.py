from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ModbusDevice(models.Model):
    _name = 'sensor_monitor.modbus.device'
    _description = 'Dispositivo Modbus'

    name = fields.Char(required=True)
    rs485_bus_id = fields.Many2one('sensor_monitor.rs485.bus', required=True)
    slave_address = fields.Integer(required=True)
    profile_id = fields.Many2one('sensor_monitor.modbus.profile', required=True)

    _sql_constraints = [
        ('unique_slave_per_bus', 'unique(rs485_bus_id, slave_address)',
         'Endereço de escravo já usado neste barramento.'),
    ]

    @api.constrains('slave_address')
    def _check_slave_address_range(self):
        for device in self:
            if not 1 <= device.slave_address <= 247:
                raise ValidationError('slave_address deve estar entre 1 e 247.')
