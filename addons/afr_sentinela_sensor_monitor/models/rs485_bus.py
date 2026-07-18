from odoo import api, fields, models

from .common import validate_code


class Rs485Bus(models.Model):
    _name = 'sensor_monitor.rs485.bus'
    _description = 'Barramento RS-485'

    hub_id = fields.Many2one('sensor_monitor.hub', required=True)
    name = fields.Char(required=True)
    bus_code = fields.Char(required=True)
    serial_port = fields.Char(required=True)
    baud_rate = fields.Integer(default=9600, required=True)
    parity = fields.Selection([
        ('none', 'Nenhuma'), ('even', 'Par'), ('odd', 'Ímpar'),
    ], default='none', required=True)
    stop_bits = fields.Selection([('1', '1'), ('2', '2')], default='1', required=True)
    data_bits = fields.Integer(default=8, required=True)

    _sql_constraints = [
        ('bus_code_unique_per_hub', 'unique(hub_id, bus_code)', 'Código de barramento já usado neste hub.'),
    ]

    @api.constrains('bus_code')
    def _check_bus_code(self):
        for bus in self:
            validate_code(bus.bus_code)
