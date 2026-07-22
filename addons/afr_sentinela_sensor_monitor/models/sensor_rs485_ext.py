from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SensorRs485Ext(models.Model):
    _inherit = 'sensor_monitor.sensor'

    modbus_register_id = fields.Many2one('sensor_monitor.modbus.profile.register')
    modbus_channel = fields.Integer(help='Canal físico no dispositivo (ex.: 1-15 no N4AIB16).')
    ma_in_min = fields.Float(default=4.0, help='Corrente mínima da entrada (mA).')
    ma_in_max = fields.Float(default=20.0, help='Corrente máxima da entrada (mA).')
    eng_out_min = fields.Float(help='Valor de engenharia correspondente a ma_in_min.')
    eng_out_max = fields.Float(help='Valor de engenharia correspondente a ma_in_max.')
    filtro_tipo = fields.Selection(
        [('none', 'Nenhum'), ('ewma', 'EWMA')], default='none', required=True)
    filtro_alpha = fields.Float(default=0.3, help='Alpha do EWMA (0-1).')

    @api.constrains('modbus_register_id', 'protocolo_origem')
    def _check_modbus_register_requires_rs485(self):
        for sensor in self:
            if sensor.modbus_register_id and sensor.protocolo_origem != 'rs485':
                raise ValidationError(
                    'modbus_register_id só pode ser definido quando protocolo_origem = rs485.'
                )
