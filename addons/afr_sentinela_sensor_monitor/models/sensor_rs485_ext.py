from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SensorRs485Ext(models.Model):
    _inherit = 'sensor_monitor.sensor'

    modbus_register_id = fields.Many2one('sensor_monitor.modbus.profile.register')

    @api.constrains('modbus_register_id', 'protocolo_origem')
    def _check_modbus_register_requires_rs485(self):
        for sensor in self:
            if sensor.modbus_register_id and sensor.protocolo_origem != 'rs485':
                raise ValidationError(
                    'modbus_register_id só pode ser definido quando protocolo_origem = rs485.'
                )
