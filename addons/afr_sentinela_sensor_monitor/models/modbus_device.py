from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ModbusDevice(models.Model):
    _name = 'sensor_monitor.modbus.device'
    _description = 'Dispositivo Modbus'

    name = fields.Char(required=True)
    rs485_bus_id = fields.Many2one('sensor_monitor.rs485.bus', required=True)
    slave_address = fields.Integer(required=True)
    profile_id = fields.Many2one('sensor_monitor.modbus.profile', required=True)
    reconexao_n = fields.Integer(
        default=3, help="Falhas seguidas antes de reabrir o serial.")
    reconexao_m = fields.Integer(
        default=5, help="Teto de reconexoes antes do cooldown.")
    reconexao_k = fields.Integer(
        default=10, help="Ciclos entre re-tentativas no cooldown.")

    _sql_constraints = [
        ('unique_slave_per_bus', 'unique(rs485_bus_id, slave_address)',
         'Endereço de escravo já usado neste barramento.'),
    ]

    @api.constrains('slave_address')
    def _check_slave_address_range(self):
        for device in self:
            if not 1 <= device.slave_address <= 247:
                raise ValidationError('slave_address deve estar entre 1 e 247.')

    @api.constrains('reconexao_n', 'reconexao_m', 'reconexao_k')
    def _check_reconexao(self):
        for device in self:
            if device.reconexao_n <= 0 or device.reconexao_m <= 0 or device.reconexao_k <= 0:
                raise ValidationError(_("reconexao_n/m/k devem ser > 0."))
